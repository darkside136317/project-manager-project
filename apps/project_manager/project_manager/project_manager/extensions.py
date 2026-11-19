"""What an industry layer adds to the core, read from the layer's hooks. The core never imports a layer.

Hooks a layer may declare (pm_construction's hooks.py is the example):

* `pm_rollup_methods = {"Label": "task_field"}` — a way to weigh leaves in the roll-up: the weight of a leaf is the
  value of that Task field (e.g. its estimate value). The label becomes a choice of Project.pm_rollup_method.
* `pm_discussion_targets = {"DocType": "dotted.path"}` — documents other than Task and Project that carry a
  discussion and photos; the function receives (name, user) and returns (project, task or None), or raises
  frappe.PermissionError when the user may not read it.
* `pm_spa_modules = ["name"]` — SPA modules to switch on (the layer's frontend/pm-module.js, found at build time).
* `pm_form_packs = ["dotted.path"]` — ready-made form templates (M3, setup/install.ensure_form_packs).
* `pm_form_events = {"approved": ["dotted.path"]}` — called with the PM Form Submission's name after a form is
  approved (an acceptance record updates the accepted quantity of its task).
* `pm_alert_types = {"Label": "dotted.path"}` — alert types of the layer (M7, services/alerts.py): the function gets
  (rule, today) and returns hits made with services.alerts._hit. The label becomes a choice of PM Alert Rule.rule_type.
* `pm_alert_rules = ["dotted.path"]` — functions returning the layer's default rules (dicts like
  constants.DEFAULT_ALERT_RULES), created once (setup/install.ensure_alert_rules).
* `pm_masters = ["dotted.path"]` — functions returning the layer's catalogues ([{"doctype", "slug", "label", "icon",
  "list_fields"}], like constants.MASTERS), shown by the generic master screens (/pm/danh-muc/<slug>).
* `pm_productivity = ["dotted.path"]` — functions (first, last) returning the quantities crews made and the man-days
  they took, per work item: [{"team", "team_name", "project", "task", "uom", "qty", "man_days"}] (M9, performance).
* `pm_conflicts = ["dotted.path"]` — functions (first, last) returning conflicts between projects the layer knows
  (machines booked twice...): [{"kind", "subject", "week", "projects": {project: share}, "message"}] (M9, workload);
  the core keeps those touching a project the viewer reads and shows the others as "Dự án khác".
* `pm_portfolio_columns = ["dotted.path"]` — functions (projects) returning {project: {key: {"label", "value",
  "format": "percent"|"number"|"currency", "tone": "good"|"warn"|"bad"|None}}} added to the portfolio rows (M9); the
  function checks what the viewer may see (finance figures...).
* `pm_reports = ["dotted.path"]` — functions returning the layer's reports (services/reports/base.Report entries) for
  the report hub, the exports and the scheduled sending (M10); each report keeps to what the user may read.
* `pm_actual_costs = ["dotted.path"]` — functions (project) returning the actual costs the layer knows:
  [{"task", "category", "amount"}] (M10, services/budget.py: earned value, budget against actual).
* `pm_dossier_parts = ["dotted.path"]` — functions (project) returning more entries of the project's dossier:
  [{"path", "content" (bytes), "source"}] (M10, services/closing.py); built as the person who asked for it.
* `project_close_handlers = ["dotted.path"]` — functions (project) called when a project is closed (M10,
  services/closing.close), e.g. an archive bridge taking the dossier.
* `pm_gate_checks = ["dotted.path"]` — conditions of passing a phase (M7, services/phases.py): the function gets the
  phase (a Task row) and returns the conditions still missing, as short sentences (empty: nothing missing).
* `pm_capabilities = ["dotted.path"]` — functions returning the layer's global capabilities: [{"code", "label",
  "module", "builtin": [Frappe roles whose built-in group starts with it]}]; permission groups may then hold them.
* `pm_project_capabilities = ["dotted.path"]` — functions returning the layer's capabilities inside a project:
  [{"code", "label"}]; project roles may then hold them (the layer adds them to the default roles itself).
* `pm_object_stores = {"collection": [("DocType", "field")]}` — the layer's kinds of objects in MinIO and the fields
  holding their keys (services/object_storage: allowed collections, and the nightly sweep keeps those keys).
* `pm_nav_items = ["dotted.path"]` — functions (user) returning sidebar entries [{"group", "label", "route", "icon"}]
  for that user (api/boot.py); "group" names an existing sidebar group or a new one.
"""

import frappe


def _last(values):
    return values[-1] if isinstance(values, list | tuple) else values


def rollup_methods() -> dict:
    """{label: Task field} of the layers' roll-up methods."""
    return {label: _last(field) for label, field in (frappe.get_hooks("pm_rollup_methods") or {}).items()}


def discussion_targets() -> dict:
    """{doctype: dotted path} of the layers' discussion targets."""
    return {doctype: _last(path) for doctype, path in (frappe.get_hooks("pm_discussion_targets") or {}).items()}


def form_event(event: str, submission) -> None:
    """Let the layers react to a form decision (in the same transaction)."""
    for path in (frappe.get_hooks("pm_form_events") or {}).get(event, []):
        frappe.get_attr(path)(submission)


def masters() -> list[dict]:
    """The layers' catalogues, after the core's (constants.MASTERS)."""
    from project_manager.project_manager import constants as C

    known = {entry["doctype"] for entry in C.MASTERS}
    out = list(C.MASTERS)
    for value in frappe.get_hooks("pm_masters") or []:
        entries = frappe.get_attr(value)() if isinstance(value, str) else [value]  # a dotted path or the entry itself
        for entry in entries:
            if isinstance(entry, dict) and entry.get("doctype") not in known:
                out.append(entry)
                known.add(entry["doctype"])
    return out


def registry() -> dict:
    """{DocType: entry} of every screen the generic API serves: the catalogues (core and layers) and administration."""
    from project_manager.project_manager import constants as C

    return {entry["doctype"]: entry for entry in [*masters(), *C.ADMIN_SCREENS]}


def spa_modules() -> list[str]:
    return sorted(set(frappe.get_hooks("pm_spa_modules") or []))


def _entries(hook: str) -> list[dict]:
    """The dicts returned by the functions a hook lists."""
    out = []
    for path in frappe.get_hooks(hook) or []:
        out.extend(entry for entry in (frappe.get_attr(path)() or []) if isinstance(entry, dict) and entry.get("code"))
    return out


def capabilities() -> list[tuple[str, str, str]]:
    """(code, label, module) of the global capabilities: the core's (constants.CAPABILITIES), then the layers'."""
    from project_manager.project_manager import constants as C

    out, known = list(C.CAPABILITIES), set(C.CAPABILITY_CODES)
    for entry in _entries("pm_capabilities"):
        if entry["code"] not in known:
            out.append((entry["code"], entry.get("label") or entry["code"], entry.get("module") or "Khác"))
            known.add(entry["code"])
    return out


def capability_codes() -> frozenset:
    return frozenset(code for code, _label, _module in capabilities())


def builtin_capabilities() -> dict:
    """{Frappe role: capabilities its group starts with}: the core's, plus what a layer grants to a built-in role."""
    from project_manager.project_manager import constants as C

    out = {role: list(codes) for role, codes in C.BUILTIN_CAPABILITIES.items()}
    for entry in _entries("pm_capabilities"):
        for role in entry.get("builtin") or ():
            if role in out and entry["code"] not in out[role]:
                out[role].append(entry["code"])
    return {role: tuple(codes) for role, codes in out.items()}


def project_capabilities() -> list[tuple[str, str]]:
    """(code, label) of the capabilities inside a project: the core's, then the layers'."""
    from project_manager.project_manager import constants as C

    out, known = list(C.PROJECT_CAPABILITIES), set(C.PROJECT_CAPABILITY_CODES)
    for entry in _entries("pm_project_capabilities"):
        if entry["code"] not in known:
            out.append((entry["code"], entry.get("label") or entry["code"]))
            known.add(entry["code"])
    return out


def project_capability_codes() -> frozenset:
    return frozenset(code for code, _label in project_capabilities())


def object_stores() -> dict:
    """{collection: [(DocType, field)]}: the layers' kinds of objects in MinIO and the fields that hold their keys."""
    out = {}
    for name, holders in (frappe.get_hooks("pm_object_stores") or {}).items():
        for holder in holders if isinstance(holders, list | tuple) else [holders]:
            pair = tuple(holder)
            if len(pair) == 2 and pair not in out.setdefault(name, []):
                out[name].append(pair)
    return out


def nav_items(user: str) -> list[dict]:
    """Sidebar entries of the layers for `user`: [{"group", "label", "route", "icon"}] (the functions check access)."""
    out = []
    for path in frappe.get_hooks("pm_nav_items") or []:
        out.extend(item for item in (frappe.get_attr(path)(user) or []) if isinstance(item, dict) and item.get("route"))
    return out
