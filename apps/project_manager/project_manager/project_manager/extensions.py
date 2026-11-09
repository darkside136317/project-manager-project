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


def spa_modules() -> list[str]:
    return sorted(set(frappe.get_hooks("pm_spa_modules") or []))
