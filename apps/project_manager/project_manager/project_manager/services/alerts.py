"""Cảnh báo (alerts): rules that watch the work and tell the right people, once, and louder when nobody reacts.

* A rule (PM Alert Rule) has a type, a few parameters, its recipients and escalation steps. The types are the core's
  (TYPES) plus those of the installed layers (hook `pm_alert_types`: {"Label": "dotted.path"}; the function gets the
  rule and the day and returns hits like the core's evaluators).
* Every morning (06:00) each active rule is evaluated: a hit is one task (or form, assignment, project) in one
  episode (usually its due date: moving the date starts a new episode). A new hit opens an alert (PM Alert, unique on
  rule + reference + episode) and notifies its recipients; an open alert whose hit is gone is closed ("Đã hết").
* Every hour, open alerts nobody acknowledged climb their rule's escalation steps (after N days → the project
  manager, a project role, the direct supervisor), and emails held back by quiet hours are sent.
* Sending twice is impossible: the alert is unique, and each (alert, level, person) notice takes a Redis key for a day.
* In one run, a person told of more than GROUP_AFTER alerts gets one notice (and one email) listing them instead of a
  stream: the first morning of a late project does not bury anyone.
* A run reads what it needs in bulk: the alerts a rule already has in one query, the new ones inserted together, and
  who works on a task, who manages a project, everyone's choices remembered for the run (`_memo`). The scheduler only
  queues the runs on the long queue (`queue_daily`, `queue_hourly`).
* In-app notices always go out; email only when the rule asks for it, an outgoing Email Account exists, the person
  keeps email on, and it is not their quiet hours (then it waits for the hourly run).
"""

import json
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, nowdate

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import can_see_task, get_access, has_project_capability, project_in
from project_manager.project_manager.services.notify import notify_user

OPEN, ACKED, OVER = "Đang mở", "Đã xác nhận", "Đã hết"
DUE_SOON, OVERDUE, AT_RISK, CRITICAL_LATE = "Sắp đến hạn", "Quá hạn", "Nguy cơ trễ", "Chậm trên đường găng"
HEALTH, NOT_ACCEPTED, STALE, FORM_WAITING, PHASE_WAITING = (
    "Đổi sức khỏe dự án", "Chưa nhận việc", "Không cập nhật", "Biểu mẫu chờ duyệt", "Chờ duyệt chuyển giai đoạn")
CLOSED_STATUSES = (C.COMPLETED, C.CANCELLED)
LIVE_PROJECTS = ("Chuẩn bị", "Đang thực hiện")
SPA_TASK, SPA_PROJECT, SPA_FORM = "/pm/cong-viec/{}", "/pm/du-an/{}/tong-quan", "/pm/bieu-mau/{}"
SPA_ALERTS = "/pm/canh-bao"
GROUP_AFTER = 3  # more notices than this for one person in one run become one
FIELDS = ["name", "rule", "rule_type", "project", "task", "reference_doctype", "reference_name", "episode", "state",
          "level", "message", "opened_on", "level_on", "closed_on", "acknowledged_by", "acknowledged_on", "recipients",
          "email_pending"]


# --- a run's memory -------------------------------------------------------------------------------------------------------

@contextmanager
def _run():
    """Remember people, preferences and visibility for the length of one run (they do not change meanwhile)."""
    outer = frappe.flags.get("pm_alert_memo")
    if outer is None:
        frappe.flags.pm_alert_memo = {}
    try:
        yield
        if outer is None:
            _flush()
    finally:
        if outer is None:
            frappe.flags.pm_alert_memo = None


def _memo(kind: str, key, compute):
    store = frappe.flags.get("pm_alert_memo")
    if store is None:
        return compute()
    bucket = store.setdefault(kind, {})
    if key not in bucket:
        bucket[key] = compute()
    return bucket[key]


def _notice(user: str, subject: str, link: str, alert) -> None:
    store = frappe.flags.get("pm_alert_memo")
    if store is None:
        notify_user(user, subject, link, "PM Alert", str(alert.name))
    else:
        store.setdefault("outbox", {}).setdefault(user, []).append((subject, link, str(alert.name), alert.rule_type))


def _mail(user: str, subject: str, link: str) -> None:
    store = frappe.flags.get("pm_alert_memo")
    if store is None:
        send_email(user, subject, link)
    else:
        store.setdefault("mail", {}).setdefault(user, []).append((subject, link))


def _flush() -> None:
    """Send what the run gathered: each notice on its own, or one per person when there are many."""
    store = frappe.flags.get("pm_alert_memo") or {}
    writes = store.pop("writes", None)
    if writes:
        _write_all(writes)
    for user, items in (store.pop("outbox", None) or {}).items():
        if len(items) <= GROUP_AFTER:
            for subject, link, name, _type in items:
                notify_user(user, subject, link, "PM Alert", name)
            continue
        counts = Counter(kind for *_rest, kind in items)
        notify_user(user, _("{0} cảnh báo mới: {1}").format(
            len(items), ", ".join(f"{kind} {count}" for kind, count in counts.most_common())), SPA_ALERTS)
    for user, items in (store.pop("mail", None) or {}).items():
        if len(items) <= GROUP_AFTER:
            for subject, link in items:
                send_email(user, subject, link)
        else:
            send_email(user, _("{0} cảnh báo mới").format(len(items)), SPA_ALERTS, lines=items)


def _write(name, **values) -> None:
    store = frappe.flags.get("pm_alert_memo")
    if store is None:
        frappe.db.set_value("PM Alert", name, values, update_modified=False)
    else:
        store.setdefault("writes", {}).setdefault(name, {}).update(values)


def _write_all(updates: dict) -> None:
    """One UPDATE per 500 alerts: each column set by a CASE on the name."""
    names = list(updates)
    for start in range(0, len(names), 500):
        chunk = names[start:start + 500]
        sets, params = [], []
        for column in sorted({c for name in chunk for c in updates[name]}):
            cases = []
            for name in chunk:
                if column in updates[name]:
                    cases.append("when %s then %s")
                    params += [name, updates[name][column]]
            sets.append(f"`{column}` = case `name` {' '.join(cases)} else `{column}` end")
        params += chunk
        frappe.db.sql(f"update `tabPM Alert` set {', '.join(sets)} where `name` in ({', '.join(['%s'] * len(chunk))})",
                      params)


def _discard() -> None:
    store = frappe.flags.get("pm_alert_memo") or {}
    for kind in ("outbox", "mail", "writes"):
        store.pop(kind, None)


# --- what the rules look at ----------------------------------------------------------------------------------------------

def _hit(reference_doctype, reference_name, project, task, episode, message, direct=()):
    return frappe._dict(reference_doctype=reference_doctype, reference_name=str(reference_name), project=project,
                        task=task, episode=str(episode), message=message, direct=list(direct))


def _label(row) -> str:
    return f"{row.pm_wbs_code or ''} {row.subject}".strip()


def _day(value) -> str:
    return getdate(value).strftime("%d/%m") if value else ""


def _leaves(rule, condition: str, params: dict) -> list:
    """Open leaf tasks of live projects matching `condition`, narrowed by the rule's node types and critical flag."""
    where = [condition, "t.is_group = 0", f"t.status not in ('{C.COMPLETED}', '{C.CANCELLED}')",
             "p.pm_is_template = 0", "ifnull(p.pm_state, 'Chuẩn bị') in %(live)s"]
    types = [line.strip() for line in (rule.node_types or "").splitlines() if line.strip()]
    if types:
        where.append("t.pm_node_type in %(types)s")
        params["types"] = tuple(types)
    if cint(rule.only_critical):
        where.append("t.pm_is_critical = 1")
    params["live"] = LIVE_PROJECTS
    return frappe.db.sql(f"""select t.name, t.subject, t.pm_wbs_code, t.project, t.exp_end_date, t.pm_forecast_end,
                                    t.pm_forecast_slip, t.pm_last_progress_on, t.progress
                             from `tabTask` t join `tabProject` p on p.name = t.project
                             where {' and '.join(where)}""", params, as_dict=True)


def due_soon(rule, today):
    days = cint(rule.days) or 2
    rows = _leaves(rule, "date(t.exp_end_date) between %(today)s and %(until)s",
                   {"today": today, "until": add_days(today, days)})
    return [_hit("Task", r.name, r.project, r.name, getdate(r.exp_end_date),
                 _("Sắp đến hạn ngày {0}: {1}").format(_day(r.exp_end_date), _label(r))) for r in rows]


def overdue(rule, today):
    rows = _leaves(rule, "date(t.exp_end_date) < %(today)s", {"today": today})
    return [_hit("Task", r.name, r.project, r.name, getdate(r.exp_end_date),
                 _("Quá hạn từ ngày {0}: {1}").format(_day(r.exp_end_date), _label(r))) for r in rows]


def at_risk(rule, today):
    rows = _leaves(rule, "t.pm_health = 'Đỏ' and date(t.exp_end_date) >= %(today)s", {"today": today})
    return [_hit("Task", r.name, r.project, r.name, getdate(r.exp_end_date),
                 _("Nguy cơ trễ: {0} dự báo xong ngày {1} (hạn {2})").format(
                     _label(r), _day(r.pm_forecast_end), _day(r.exp_end_date))) for r in rows]


def critical_late(rule, today):
    rows = _leaves(rule, "t.pm_is_critical = 1 and t.pm_forecast_slip > 0", {})
    return [_hit("Task", r.name, r.project, r.name, getdate(r.exp_end_date),
                 _("Việc găng chậm {0} ngày: {1} (cả dự án chậm theo)").format(r.pm_forecast_slip, _label(r)))
            for r in rows]


def stale(rule, today):
    days = cint(rule.days) or 5
    rows = _leaves(rule, "t.progress > 0 and t.progress < 100 and t.pm_last_progress_on < %(before)s",
                   {"before": add_days(today, -days)})
    return [_hit("Task", r.name, r.project, r.name, getdate(r.pm_last_progress_on),
                 _("{0} ngày không cập nhật tiến độ: {1}").format((getdate(today) - getdate(r.pm_last_progress_on)).days,
                                                               _label(r))) for r in rows]


def not_accepted(rule, today):
    days = cint(rule.days) or 2
    rows = frappe.db.sql("""select a.name, a.task, a.user, a.raci, a.assigned_on, t.project, t.subject, t.pm_wbs_code
                            from `tabPM Task Assignment` a join `tabTask` t on t.name = a.task
                            join `tabProject` p on p.name = t.project
                            where a.is_active = 1 and a.state = %(pending)s and ifnull(a.user, '') != ''
                              and a.assigned_on < %(before)s and p.pm_is_template = 0""",
                         {"pending": C.PENDING, "before": add_days(today, -days)}, as_dict=True)
    return [_hit("PM Task Assignment", r.name, r.project, r.task, r.name,
                 _("Chưa nhận việc sau {0} ngày: {1} ({2})").format(days, _label(r), r.raci), direct=[r.user])
            for r in rows]


def form_waiting(rule, today):
    days = cint(rule.days) or 2
    rows = frappe.db.sql("""select s.name, s.title, s.project, s.task, s.submitted_on from `tabPM Form Submission` s
                            where s.state = %(submitted)s and s.submitted_on < %(before)s""",
                         {"submitted": C.SUB_SUBMITTED, "before": add_days(today, -days)}, as_dict=True)
    return [_hit("PM Form Submission", r.name, r.project, r.task, r.name,
                 _("Biểu mẫu chờ duyệt từ ngày {0}: {1}").format(_day(r.submitted_on), r.title)) for r in rows]


def phase_waiting(rule, today):
    rows = frappe.db.sql("""select name, subject, pm_wbs_code, project from `tabTask`
                            where pm_gate_state = 'Chờ duyệt' and status != %s""", C.CANCELLED, as_dict=True)
    return [_hit("Task", r.name, r.project, r.name, "cho-duyet",
                 _("Giai đoạn {0} đã đủ điều kiện, chờ duyệt chuyển sang giai đoạn sau").format(_label(r))) for r in rows]


# In the order of PM Alert Rule.rule_type (a core-only site needs no Property Setter).
TYPES = {DUE_SOON: due_soon, OVERDUE: overdue, AT_RISK: at_risk, CRITICAL_LATE: critical_late, HEALTH: None,
         NOT_ACCEPTED: not_accepted, STALE: stale, FORM_WAITING: form_waiting, PHASE_WAITING: phase_waiting}


def types() -> dict:
    """{label: evaluator} of the core's types and the installed layers' (None: raised by an event, not evaluated)."""
    out = dict(TYPES)
    for label, path in (frappe.get_hooks("pm_alert_types") or {}).items():
        out[label] = frappe.get_attr(path[-1] if isinstance(path, list) else path)
    return out


# --- who hears of it -----------------------------------------------------------------------------------------------------

def _task_people(task: str) -> dict:
    return _people_of([task])[task]


def _people_of(tasks) -> dict:
    """{task: {"accountable", "responsible", "reviewer": users}} from the live assignments and the task's reviewer."""
    tasks = list(dict.fromkeys(t for t in tasks if t))
    out = {task: {"accountable": set(), "responsible": set(), "reviewer": set()} for task in tasks}
    keys = {C.ACCOUNTABLE: "accountable", C.RESPONSIBLE: "responsible", C.REVIEWER: "reviewer"}
    for start in range(0, len(tasks), 500):
        chunk = tasks[start:start + 500]
        rows = frappe.get_all("PM Task Assignment", filters={"task": ["in", chunk], "is_active": 1,
                                                             "state": ["in", C.LIVE_STATES]},
                              fields=["task", "raci", "user", "team"], limit_page_length=0)
        teams = {row.team for row in rows if row.team and not row.user}
        crews = {}
        if teams:
            for member in frappe.get_all("PM Team Member", filters={"parent": ["in", list(teams)]}, fields=["parent", "user"],
                                         limit_page_length=0):
                crews.setdefault(member.parent, set()).add(member.user)
        for row in rows:
            key = keys.get(row.raci)
            if key:
                out[row.task][key].update(u for u in ([row.user] if row.user else crews.get(row.team, ())) if u)
        for task, reviewer in frappe.get_all("Task", filters={"name": ["in", chunk], "pm_reviewer": ["is", "set"]},
                                             fields=["name", "pm_reviewer"], as_list=True):
            out[task]["reviewer"].add(reviewer)
    return out


def _prefetch_people(tasks) -> None:
    """Fill the run's memory with the people of these tasks at once."""
    store = frappe.flags.get("pm_alert_memo")
    if store is None:
        return
    bucket = store.setdefault("task_people", {})
    bucket.update(_people_of([t for t in set(tasks) if t and t not in bucket]))


def _role_people(project: str, role: str) -> set:
    return set(frappe.get_all("PM Project Member", filters={"project": project, "project_role": role, "is_active": 1},
                              pluck="user"))


def _supervisors(users) -> set:
    out = set()
    for user in users:
        boss = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "reports_to")
        if boss:
            boss_user = frappe.db.get_value("Employee", boss, "user_id")
            if boss_user:
                out.add(boss_user)
    return out


def _manager(project: str):
    return _memo("manager", project, lambda: frappe.db.get_value("Project", project, "pm_manager"))


def _enabled(user: str) -> bool:
    return _memo("enabled", user, lambda: bool(frappe.db.get_value("User", user, "enabled")))


def _may_see(user: str, task, project) -> bool:
    def look():
        if task:
            return can_see_task(task, project, user)
        return not project or project_in(get_access(user).read, project)
    return _memo("sees", (user, task, project), look)


def recipients(step, hit) -> set:
    """Users a rule (or one of its escalation steps) reaches for this hit, who may also read what it is about."""
    users = set(hit.direct or [])
    base = set()
    if hit.task and any(cint(step.get(k)) for k in ("to_accountable", "to_responsible", "to_reviewer", "to_followers",
                                                    "to_supervisor")):
        people = _memo("task_people", hit.task, lambda: _task_people(hit.task))
        if cint(step.get("to_accountable")):
            users |= people["accountable"]
        if cint(step.get("to_responsible")):
            users |= people["responsible"]
        if cint(step.get("to_reviewer")):
            users |= people["reviewer"]
        if cint(step.get("to_followers")):
            users |= _memo("followers", hit.task, lambda: set(frappe.get_all(
                "PM Follow", filters={"reference_doctype": "Task", "reference_name": hit.task, "watching": 1}, pluck="user")))
        base = people["accountable"] | people["responsible"]
    if cint(step.get("to_manager")) and hit.project:
        manager = _manager(hit.project)
        if manager:
            users.add(manager)
    if step.get("to_role") and hit.project:
        role = step.get("to_role")
        users |= _memo("role", (hit.project, role), lambda: _role_people(hit.project, role))
    if cint(step.get("to_supervisor")):
        users |= _memo("bosses", frozenset(base or users), lambda: _supervisors(base or users))
    return {user for user in users if user and user not in ("Guest", "Administrator") and _enabled(user)
            and _may_see(user, hit.task, hit.project)}


# --- preferences, quiet hours, email -------------------------------------------------------------------------------------

def preference(user: str) -> frappe._dict:
    row = frappe.db.get_value("PM Notification Preference", user, ["email", "quiet_start", "quiet_end", "digest_daily",
                                                                   "digest_weekly", "muted_types"], as_dict=True)
    single = frappe.get_cached_doc("PM Settings")
    row = row or frappe._dict(email=1, digest_daily=1, digest_weekly=1, muted_types="")
    row.quiet_start = row.get("quiet_start") or single.get("quiet_start")
    row.quiet_end = row.get("quiet_end") or single.get("quiet_end")
    row.muted = {line.strip() for line in (row.get("muted_types") or "").splitlines() if line.strip()}
    return row


def _minutes(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds() // 60) % 1440
    parts = str(value).split(":")
    return int(parts[0]) * 60 + int(parts[1] if len(parts) > 1 else 0)


def quiet(pref, moment=None) -> bool:
    """Is `moment` within the person's quiet hours (a window may cross midnight: 21:00 → 07:00)?"""
    start, end = _minutes(pref.quiet_start), _minutes(pref.quiet_end)
    if start is None or end is None or start == end:
        return False
    moment = get_datetime(moment or now_datetime())
    now = moment.hour * 60 + moment.minute
    return start <= now < end if start < end else (now >= start or now < end)


def email_ready() -> bool:
    return bool(frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}))


def send_email(user: str, subject: str, link: str, lines=None) -> None:
    """One email; `lines`: [(text, link)] listed in it (a grouped email)."""
    address = frappe.db.get_value("User", user, "email")
    if not address:
        return
    escape = frappe.utils.escape_html
    url = frappe.utils.get_url(link)
    body = f"<p>{escape(subject)}</p>"
    if lines:
        items = "".join(f'<li><a href="{frappe.utils.get_url(target)}">{escape(text)}</a></li>' for text, target in lines[:50])
        more = f"<p>{_('và {0} cảnh báo khác').format(len(lines) - 50)}</p>" if len(lines) > 50 else ""
        body += f"<ul>{items}</ul>{more}"
    body += f'<p><a href="{url}">{_("Mở trong ứng dụng")}</a></p>'
    frappe.sendmail(recipients=[address], subject=subject, message=body, delayed=True)


def _link(alert) -> str:
    if alert.reference_doctype == "PM Form Submission":
        return SPA_FORM.format(alert.reference_name)
    if alert.task:
        return SPA_TASK.format(alert.task)
    return SPA_PROJECT.format(alert.project)


# --- opening, escalating, closing --------------------------------------------------------------------------------------

def _users(value) -> list:
    try:
        return list(json.loads(value or "[]"))
    except ValueError:
        return []


def deliver(alert, users, level: int, rule=None) -> list:
    """Notify these users of this alert at this level, at most once each (Redis key for a day). Returns who was told."""
    rule = rule or frappe.get_cached_doc("PM Alert Rule", alert.rule)
    told, pending = [], set(_users(alert.email_pending))
    subject = (_("[Leo thang bậc {0}] ").format(level) if level else "") + f"[{alert.rule_type}] {alert.message}"
    use_email = cint(rule.send_email) and email_ready()
    for user in sorted(users):
        pref = _memo("pref", user, lambda u=user: preference(u))
        if alert.rule_type in pref.muted:
            continue
        if not _claim(f"pm_alert_sent|{frappe.local.site}|{alert.name}|{level}|{user}"):
            continue  # already told (two runs at once)
        _notice(user, subject, _link(alert), alert)
        told.append(user)
        if use_email and cint(pref.email):
            if quiet(pref):
                pending.add(user)
            else:
                _mail(user, subject, _link(alert))
    everyone = sorted(set(_users(alert.recipients)) | set(told))
    alert.recipients = json.dumps(everyone)  # several levels may be delivered in one run
    alert.email_pending = json.dumps(sorted(pending)) if pending else None
    _write(alert.name, recipients=alert.recipients, email_pending=alert.email_pending)
    return told


def _claim(key: str) -> bool:
    """SET NX for a day: True the first time this key is claimed."""
    try:
        return bool(frappe.cache.set(key, 1, nx=True, ex=86400))
    except TypeError:  # an older redis client wrapper without nx: fall back on a read then write
        if frappe.cache.get(key):
            return False
        frappe.cache.set(key, 1, ex=86400)
        return True


def _open(rule, hit, now) -> tuple:
    """(alert, created) for this hit: the existing one of the episode, or a new one."""
    filters = {"rule": rule.name, "reference_doctype": hit.reference_doctype, "reference_name": hit.reference_name,
               "episode": hit.episode}
    existing = frappe.db.get_value("PM Alert", filters, FIELDS, as_dict=True)
    if existing:
        return existing, False
    doc = frappe.get_doc({"doctype": "PM Alert", "rule": rule.name, "rule_type": rule.rule_type, "project": hit.project,
                          "task": hit.task, "reference_doctype": hit.reference_doctype,
                          "reference_name": hit.reference_name, "episode": hit.episode, "state": OPEN, "level": 0,
                          "message": hit.message[:1000], "opened_on": now, "recipients": "[]"})
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:  # another run opened it at the same moment
        return frappe.db.get_value("PM Alert", filters, FIELDS, as_dict=True), False
    return frappe._dict(doc.as_dict()), True


def raise_hit(rule, hit, now=None) -> tuple:
    """Open (or find) the alert of a hit and tell its recipients when it is new. Returns (alert, created)."""
    now = now or now_datetime()
    alert, created = _open(rule, hit, now)
    if created:
        alert.direct = hit.direct
        deliver(alert, recipients(rule, hit), 0, rule)
    return alert, created


def _key(row) -> tuple:
    return (row.reference_doctype, str(row.reference_name), str(row.episode))


def evaluate_rule(rule, today=None) -> dict:
    """Open the new hits of one rule, close its alerts whose condition is gone."""
    today = getdate(today or nowdate())
    evaluator = types().get(rule.rule_type)
    if evaluator is None:
        return {"opened": 0, "closed": 0}
    now = now_datetime()
    with _run():
        hits = {}
        for hit in evaluator(rule, today):
            hits.setdefault(_key(hit), hit)
        live = {_key(row): row for row in frappe.get_all(
            "PM Alert", filters={"rule": rule.name, "state": ["in", [OPEN, ACKED]]}, fields=FIELDS, limit_page_length=0)}
        created = _open_many(rule, [hit for key, hit in hits.items() if key not in live], now)
        _prefetch_people(hit.task for _alert, hit in created)
        for alert, hit in created:
            alert.direct = hit.direct
            deliver(alert, recipients(rule, hit), 0, rule)
        gone = [row.name for key, row in live.items() if key not in hits]
        for chunk in range(0, len(gone), 500):
            frappe.db.sql("update `tabPM Alert` set state = %s, closed_on = %s where name in %s",
                          (OVER, now, tuple(gone[chunk:chunk + 500])))
    return {"opened": len(created), "closed": len(gone)}


def _open_many(rule, hits: list, now) -> list:
    """[(alert, hit)] opened for these hits, none of which has a live alert: an alert of the same episode that was over
    opens again, the others are inserted together."""
    if not hits:
        return []
    out, fresh = [], []
    names = list({hit.reference_name for hit in hits})
    over = {}
    for chunk in range(0, len(names), 500):
        for row in frappe.get_all("PM Alert", filters={"rule": rule.name, "state": OVER,
                                                       "reference_name": ["in", names[chunk:chunk + 500]]},
                                  fields=FIELDS, limit_page_length=0):
            over[_key(row)] = row
    for hit in hits:
        row = over.get(_key(hit))
        if row:  # the condition came back within the same episode (a finished task reopened)
            frappe.db.set_value("PM Alert", row.name, {"state": OPEN, "closed_on": None, "level": 0, "level_on": None,
                                                       "opened_on": now, "acknowledged_by": None, "acknowledged_on": None},
                                update_modified=False)
            row.update(state=OPEN, level=0, opened_on=now)
            out.append((row, hit))
        else:
            fresh.append(hit)
    if fresh:
        from project_manager.project_manager.services.queries import reserve_ids

        user = frappe.session.user
        columns = ("name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "rule", "rule_type",
                   "project", "task", "reference_doctype", "reference_name", "episode", "state", "level", "message",
                   "opened_on", "recipients")
        ids = reserve_ids("PM Alert", len(fresh))
        rows = [(number, now, now, user, user, 0, 0, rule.name, rule.rule_type, hit.project, hit.task,
                 hit.reference_doctype, hit.reference_name, hit.episode, OPEN, 0, hit.message[:1000], now, "[]")
                for number, hit in zip(ids, fresh, strict=True)]
        frappe.db.bulk_insert("PM Alert", columns, rows, ignore_duplicates=True, chunk_size=500)  # a run at the same time
        mine = {row.name: row for chunk in range(0, len(ids), 500) for row in frappe.get_all(
            "PM Alert", filters={"name": ["in", ids[chunk:chunk + 500]]}, fields=FIELDS, limit_page_length=0)}
        out += [(mine[number], hit) for number, hit in zip(ids, fresh, strict=True) if number in mine]
    return out


def _rules():
    return [frappe.get_doc("PM Alert Rule", name) for name in
            frappe.get_all("PM Alert Rule", filters={"is_active": 1}, pluck="name", order_by="name asc")]


def queue_daily() -> None:
    """Scheduler, 06:00: the run goes to the long queue (many projects make it longer than a scheduled job may last)."""
    from project_manager.project_manager.services import jobs

    jobs.enqueue_once("project_manager.project_manager.services.alerts.run_daily", "pm-alerts-daily", "long",
                      timeout=3600, enqueue_after_commit=False)


def queue_hourly() -> None:
    from project_manager.project_manager.services import jobs

    jobs.enqueue_once("project_manager.project_manager.services.alerts.run_hourly", "pm-alerts-hourly", "long",
                      timeout=1800, enqueue_after_commit=False)


def run_daily(today=None) -> dict:
    """Every active rule, then the escalations."""
    out = {}
    off = frappe.get_all("PM Alert Rule", filters={"is_active": 0}, pluck="name")
    if off:  # a rule turned off: its alerts are over
        frappe.db.sql("update `tabPM Alert` set state = %s, closed_on = %s where rule in %s and state in %s",
                      (OVER, now_datetime(), tuple(off), (OPEN, ACKED)))
    with _run():
        for rule in _rules():
            try:
                out[rule.name] = evaluate_rule(rule, today)
                _flush()  # this rule's notices, with its alerts
                frappe.db.commit()
            except Exception:
                _discard()
                frappe.db.rollback()
                frappe.log_error(f"Cảnh báo: quy tắc {rule.name}", frappe.get_traceback())
        out["escalated"] = escalate()
    frappe.db.commit()
    return out


def run_hourly() -> dict:
    """Escalations, and the emails that waited for the end of someone's quiet hours."""
    with _run():
        escalated = escalate()
        _flush()  # what escalation wrote, before the waiting emails are read
        out = {"escalated": escalated, "emails": send_pending_emails()}
    frappe.db.commit()
    return out


def escalate(now=None) -> int:
    """Open alerts nobody acknowledged climb the steps of their rule (after N days since they opened)."""
    now = get_datetime(now or now_datetime())
    active = frappe.get_all("PM Alert Rule", filters={"is_active": 1}, pluck="name")
    rules = {name: frappe.get_doc("PM Alert Rule", name) for name in active}  # a rule turned off does not climb
    steps = {name: sorted(rule.escalations, key=lambda s: cint(s.after_days)) for name, rule in rules.items()}
    with _run():
        climbing = []
        for alert in frappe.get_all("PM Alert", filters={"state": OPEN}, fields=FIELDS, limit_page_length=0):
            ladder = steps.get(alert.rule) or []
            days = (now.date() - get_datetime(alert.opened_on).date()).days
            target = max((i + 1 for i, step in enumerate(ladder) if days >= cint(step.after_days)), default=0)
            if target > cint(alert.level):
                climbing.append((alert, target))
        _prefetch_people(alert.task for alert, _target in climbing
                         if any(cint(step.to_supervisor) for step in steps[alert.rule]))
        for alert, target in climbing:
            hit = _hit(alert.reference_doctype, alert.reference_name, alert.project, alert.task, alert.episode,
                       alert.message)
            for level in range(cint(alert.level) + 1, target + 1):
                deliver(alert, recipients(steps[alert.rule][level - 1].as_dict(), hit), level, rules[alert.rule])
            _write(alert.name, level=target, level_on=now)
    return len(climbing)


def send_pending_emails(now=None) -> int:
    sent = 0
    if not email_ready():
        return 0
    for alert in frappe.get_all("PM Alert", filters={"email_pending": ["is", "set"]}, fields=FIELDS, limit_page_length=0):
        waiting = _users(alert.email_pending)
        left = []
        subject = (_("[Leo thang bậc {0}] ").format(alert.level) if cint(alert.level) else "") + \
            f"[{alert.rule_type}] {alert.message}"
        for user in waiting:
            if quiet(preference(user), now):
                left.append(user)
            else:
                _mail(user, subject, _link(alert))
                sent += 1
        frappe.db.set_value("PM Alert", alert.name, "email_pending", json.dumps(left) if left else None,
                            update_modified=False)
    return sent


def health_changed(project: str, before: str, after: str, reason: str) -> None:
    """risk.py: the project's health changed. Worse opens an alert of the "Đổi sức khỏe dự án" rules; back to Xanh
    closes them."""
    from project_manager.project_manager.services.risk import RANK

    now = now_datetime()
    for rule in [r for r in _rules() if r.rule_type == HEALTH]:
        if RANK.get(after, 0) > RANK.get(before, 0):
            name = frappe.db.get_value("Project", project, "project_name")
            hit = _hit("Project", project, project, None, f"{after}:{nowdate()}",
                       _("Sức khỏe dự án {0}: {1} → {2}{3}").format(name, before, after, f" ({reason})" if reason else ""))
            raise_hit(rule, hit, now)
        elif after == "Xanh":
            for row in frappe.get_all("PM Alert", filters={"rule": rule.name, "reference_doctype": "Project",
                                                           "reference_name": project, "state": ["in", [OPEN, ACKED]]},
                                      pluck="name"):
                frappe.db.set_value("PM Alert", row, {"state": OVER, "closed_on": now}, update_modified=False)


# --- reading and acknowledging -------------------------------------------------------------------------------------------

def _decorate(rows) -> list:
    projects = {r.project for r in rows if r.project}
    names = dict(frappe.get_all("Project", filters={"name": ["in", list(projects)]}, fields=["name", "project_name"],
                                as_list=True)) if projects else {}
    for row in rows:
        row["project_name"] = names.get(row.project)
        row["link"] = _link(row)
        row["recipients"] = _users(row.recipients)
        row.pop("email_pending", None)
    return rows


def mine(state: str = "open", limit=100) -> dict:
    """Alerts the user was told of (open first)."""
    user = frappe.session.user
    states = [OPEN, ACKED] if state == "open" else [OVER] if state == "closed" else [OPEN, ACKED, OVER]
    rows = frappe.get_list("PM Alert", filters={"state": ["in", states], "recipients": ["like", f'%"{user}"%']},
                           fields=FIELDS, order_by="name desc", limit_page_length=max(1, min(cint(limit) or 100, 300)))
    order = {OPEN: 0, ACKED: 1, OVER: 2}
    rows.sort(key=lambda r: (order.get(r.state, 3), -cint(r.level), -cint(r.name)))  # open and highest first
    return {"alerts": _decorate(rows), "open": frappe.db.count("PM Alert", {"state": OPEN,
                                                                            "recipients": ["like", f'%"{user}"%']})}


def of_project(project: str, state: str = "open", limit=200) -> list:
    if not project_in(get_access().read, project):
        raise frappe.PermissionError(_("Bạn không xem được dự án này"))
    states = [OPEN, ACKED] if state == "open" else [OVER] if state == "closed" else [OPEN, ACKED, OVER]
    return _decorate(frappe.get_list("PM Alert", filters={"project": project, "state": ["in", states]}, fields=FIELDS,
                                     order_by="level desc, name desc", limit_page_length=max(1, min(cint(limit), 500))))


def acknowledge(name, note: str = "") -> dict:
    """"Đã biết, đang xử lý": no more escalation. Whoever was told, or may plan or approve in the project."""
    alert = frappe.db.get_value("PM Alert", cint(name), FIELDS, as_dict=True)
    if not alert:
        raise frappe.DoesNotExistError(_("Không tìm thấy cảnh báo"))
    user = frappe.session.user
    if user not in _users(alert.recipients) and not has_project_capability(alert.project, "plan.edit", "task.approve"):
        raise frappe.PermissionError(_("Cảnh báo này không gửi cho bạn"))
    if alert.state != OPEN:
        return _decorate([alert])[0]
    frappe.db.set_value("PM Alert", alert.name, {"state": ACKED, "acknowledged_by": user,
                                                 "acknowledged_on": now_datetime()}, update_modified=False)
    if alert.task:
        from project_manager.project_manager.services import activity

        activity.record("Task", alert.task, "Hệ thống", _("Đã xác nhận cảnh báo: {0}{1}").format(
            alert.message, f" ({note.strip()})" if (note or "").strip() else ""))
    alert.update(state=ACKED, acknowledged_by=user)
    return _decorate([alert])[0]


def save_preference(values: dict) -> dict:
    user = frappe.session.user
    if isinstance(values, str):
        values = json.loads(values or "{}")
    allowed = {k: values.get(k) for k in ("email", "quiet_start", "quiet_end", "digest_daily", "digest_weekly",
                                         "muted_types") if k in values}
    for key in ("email", "digest_daily", "digest_weekly"):
        if key in allowed:
            allowed[key] = cint(allowed[key])
    for key in ("quiet_start", "quiet_end"):
        if key in allowed and allowed[key] in ("",):
            allowed[key] = None
    if frappe.db.exists("PM Notification Preference", user):
        frappe.db.set_value("PM Notification Preference", user, allowed)
    else:
        frappe.get_doc({"doctype": "PM Notification Preference", "user": user, **allowed}).insert(ignore_permissions=True)
    return my_preference()


def my_preference() -> dict:
    pref = preference(frappe.session.user)
    return {"email": cint(pref.email), "quiet_start": _clock(pref.quiet_start), "quiet_end": _clock(pref.quiet_end),
            "digest_daily": cint(pref.digest_daily), "digest_weekly": cint(pref.digest_weekly),
            "muted_types": sorted(pref.muted), "types": sorted(types()), "email_ready": email_ready()}


def _clock(value) -> str:
    minutes = _minutes(value)
    return "" if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"
