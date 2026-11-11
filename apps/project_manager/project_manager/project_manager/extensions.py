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
* `pm_gate_checks = ["dotted.path"]` — conditions of passing a phase (M7, services/phases.py): the function gets the
  phase (a Task row) and returns the conditions still missing, as short sentences (empty: nothing missing).
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
