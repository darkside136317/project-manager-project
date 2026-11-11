"""Chuyển giai đoạn (phase gates): the project moves from one phase to the next when the phase is done and its
conditions are met.

* The phases are the project's top-level groups, in their order. The current phase is the first not passed yet
  (Project.pm_current_phase).
* Conditions of a phase: all its work is finished (its roll-up status is Completed, which already waits for the forms
  it requires, M3), plus what the installed layers ask through the hook `pm_gate_checks` (dotted paths of functions
  that get the phase and return the conditions still missing: the construction layer asks for every work item to be
  accepted in full).
* What happens when they are met depends on the phase's mode (Task.pm_gate_mode, by default its node type's
  default_gate_mode): Tự động — it passes at once; Cần duyệt — it waits ("Chờ duyệt") for the project manager, who is
  told (and the alert rule "Chờ duyệt chuyển giai đoạn" reminds them); Thủ công — the manager passes it when ready.
* Passing a phase records it in the project's history, makes the next phase current and tells its people.
"""

import frappe
from frappe import _
from frappe.utils import cint

from project_manager.project_manager import constants as C
from project_manager.project_manager.policy import has_project_capability
from project_manager.project_manager.services import activity, gates
from project_manager.project_manager.services.notify import notify_user

MANUAL, APPROVAL, AUTO = "Thủ công", "Cần duyệt", "Tự động"
WAITING, PASSED = "Chờ duyệt", "Đã chuyển"
SPA_OVERVIEW = "/pm/du-an/{}/tong-quan"
FIELDS = ["name", "subject", "pm_wbs_code", "pm_path", "status", "progress", "pm_node_type", "pm_gate_mode",
          "pm_gate_state", "pm_accountable", "project"]


def phases_of(project: str) -> list:
    return frappe.db.sql(f"""select {', '.join(FIELDS)} from `tabTask`
                             where project = %s and is_group = 1 and ifnull(parent_task, '') = '' and status != %s
                             order by pm_path asc""", (project, C.CANCELLED), as_dict=True)


def mode_of(row) -> str:
    if row.get("pm_gate_mode"):
        return row.pm_gate_mode
    default = frappe.get_cached_value("PM Node Type", row.pm_node_type, "default_gate_mode") if row.get("pm_node_type") else None
    return default or MANUAL


def unmet(phase) -> list[str]:
    """What still keeps this phase from passing."""
    missing = []
    if phase.status != C.COMPLETED:
        left = frappe.db.sql("""select count(*) from `tabTask` where project = %s and is_group = 0
                                and pm_path like %s and status not in %s""",
                             (phase.project, f"{phase.pm_path}.%", (C.COMPLETED, C.CANCELLED)))[0][0]
        if cint(left):
            missing.append(_("còn {0} việc chưa xong").format(left))
        else:
            missing.append(_("giai đoạn chưa hoàn thành"))
    forms = gates.unmet(phase.name)
    if forms:
        missing.append(_("chờ biểu mẫu đã duyệt: {0}").format(", ".join(forms)))
    for path in frappe.get_hooks("pm_gate_checks") or []:
        missing += list(frappe.get_attr(path)(phase) or [])
    return missing


def state(project: str) -> dict | None:
    """The current phase as the overview shows it."""
    rows = phases_of(project)
    current = next((row for row in rows if row.pm_gate_state != PASSED), None)
    if not current:
        return {"phases": len(rows), "done": len(rows), "current": None} if rows else None
    index = rows.index(current)
    missing = unmet(current)
    return {
        "phases": len(rows), "done": index, "current": {
            "name": current.name, "label": f"{current.pm_wbs_code or ''} {current.subject}".strip(),
            "progress": current.progress, "mode": mode_of(current), "state": current.pm_gate_state or None,
            "missing": missing, "next": (f"{rows[index + 1].pm_wbs_code or ''} {rows[index + 1].subject}".strip()
                                         if index + 1 < len(rows) else None),
            "can_pass": not missing and may_pass(project)},
    }


def may_pass(project: str) -> bool:
    return has_project_capability(project, "plan.edit", "project.edit")


def check(project: str) -> dict | None:
    """Look at the current phase: pass it (Tự động), ask for approval (Cần duyệt), or wait. Several automatic phases
    in a row may pass at once."""
    for _round in range(10):
        rows = phases_of(project)
        current = next((row for row in rows if row.pm_gate_state != PASSED), None)
        stored = frappe.db.get_value("Project", project, "pm_current_phase")
        if (current.name if current else None) != stored:
            frappe.db.set_value("Project", project, "pm_current_phase", current.name if current else None,
                                update_modified=False)
        if not current:
            return None
        missing = unmet(current)
        mode = mode_of(current)
        if missing:
            if current.pm_gate_state == WAITING:  # it was ready, then something reopened
                frappe.db.set_value("Task", current.name, "pm_gate_state", None, update_modified=False)
            return {"phase": current.name, "missing": missing}
        if mode == AUTO:
            _advance(project, rows, current, None)
            continue
        if mode == APPROVAL and current.pm_gate_state != WAITING:
            frappe.db.set_value("Task", current.name, "pm_gate_state", WAITING, update_modified=False)
            activity.record("Task", current.name, "Trạng thái",
                            _("Giai đoạn đủ điều kiện, chờ quản lý dự án duyệt chuyển sang giai đoạn sau"))
            manager = frappe.db.get_value("Project", project, "pm_manager")
            if manager:
                notify_user(manager, _("Giai đoạn {0} đủ điều kiện: chờ bạn duyệt chuyển giai đoạn").format(current.subject),
                            SPA_OVERVIEW.format(project), "Task", current.name)
        return {"phase": current.name, "missing": [], "mode": mode}
    return None


def pass_phase(phase: str, note: str = "") -> dict:
    """The manager passes the current phase (Cần duyệt, or Thủ công) once its conditions are met."""
    project = frappe.db.get_value("Task", phase, "project")
    if not project or not may_pass(project):
        raise frappe.PermissionError(_("Chỉ người lập kế hoạch dự án mới chuyển được giai đoạn"))
    frappe.db.sql("select name from `tabProject` where name = %s for update", project)
    rows = phases_of(project)
    current = next((row for row in rows if row.pm_gate_state != PASSED), None)
    if not current or current.name != phase:
        frappe.throw(_("Đây không phải giai đoạn hiện tại của dự án"))
    missing = unmet(current)
    if missing:
        frappe.throw(_("Chưa đủ điều kiện: {0}").format("; ".join(missing)), title=_("Chưa chuyển được giai đoạn"))
    _advance(project, rows, current, frappe.session.user, note)
    check(project)  # the next one may already be ready
    return state(project)


def _advance(project, rows, current, user, note: str = "") -> None:
    frappe.db.set_value("Task", current.name, "pm_gate_state", PASSED, update_modified=False)
    index = rows.index(current)
    following = rows[index + 1] if index + 1 < len(rows) else None
    frappe.db.set_value("Project", project, "pm_current_phase", following.name if following else None,
                        update_modified=False)
    who = _("tự động") if not user else (frappe.db.get_value("User", user, "full_name") or user)
    text = (_("Chuyển từ giai đoạn {0} sang {1} ({2})").format(current.subject, following.subject, who) if following
            else _("Hoàn thành giai đoạn cuối {0} ({1})").format(current.subject, who))
    activity.record("Project", project, "Trạng thái", text + (f": {note.strip()}" if (note or "").strip() else ""),
                    data={"phase": current.name, "next": following.name if following else None})
    people = {frappe.db.get_value("Project", project, "pm_manager")}
    if following and following.pm_accountable:
        people.add(following.pm_accountable)
    for person in people - {None, user}:
        notify_user(person, text, SPA_OVERVIEW.format(project), "Project", project)


def check_all() -> int:
    """Nightly safety net: every live project."""
    count = 0
    for project in frappe.get_all("Project", filters={"pm_is_template": 0, "pm_state": ["in", ["Chuẩn bị", "Đang thực hiện"]]},
                                  pluck="name"):
        try:
            check(project)
            frappe.db.commit()
            count += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(f"Chuyển giai đoạn {project}", frappe.get_traceback())
    return count
