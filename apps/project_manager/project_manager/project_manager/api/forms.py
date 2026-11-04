"""Dynamic forms: templates and their versions, filling in, approving, PDF, Excel, requirements on tasks.
Rules live in services/form_templates.py, services/forms.py, services/form_output.py and services/gates.py."""

import frappe

from project_manager.project_manager.services import form_output, form_templates, forms, gates
from project_manager.project_manager.services.ui import assert_staff


def _json(value):
    return frappe.parse_json(value) if isinstance(value, str) else value


def _file(filename: str, content: bytes, kind: str = "download") -> None:
    frappe.response["filename"] = filename
    frappe.response["filecontent"] = content
    frappe.response["type"] = kind


# --- templates ----------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def templates_overview():
    assert_staff()
    return form_templates.overview()


@frappe.whitelist()
def templates_in_use():
    assert_staff()
    return form_templates.in_use()


@frappe.whitelist()
def template(name):
    assert_staff()
    return form_templates.get(name)


@frappe.whitelist(methods=["POST"])
def template_create(code, values, rows=None):
    assert_staff()
    return form_templates.create(code, _json(values), _json(rows))


@frappe.whitelist(methods=["POST"])
def template_save(name, values, rows=None):
    assert_staff()
    return form_templates.save(name, _json(values), _json(rows))


@frappe.whitelist(methods=["POST"])
def template_activate(name):
    assert_staff()
    return form_templates.activate(name)


@frappe.whitelist(methods=["POST"])
def template_retire(name):
    assert_staff()
    return form_templates.retire(name)


@frappe.whitelist(methods=["POST"])
def template_new_version(name):
    assert_staff()
    return form_templates.new_version(name)


@frappe.whitelist(methods=["POST"])
def template_remove(name):
    assert_staff()
    return form_templates.remove_draft(name)


# --- filled-in forms ----------------------------------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def start(template_code, project=None, task=None, client_uuid=None):
    assert_staff()
    return forms.start(template_code, project or None, task or None, client_uuid or None)


@frappe.whitelist()
def detail(name):
    assert_staff()
    return forms.detail(name)


@frappe.whitelist(methods=["POST"])
def save(name, data):
    assert_staff()
    return forms.save(name, _json(data))


@frappe.whitelist(methods=["POST"])
def submit(name, data=None):
    assert_staff()
    return forms.submit(name, _json(data) if data not in (None, "") else None)


@frappe.whitelist(methods=["POST"])
def approve(name, note=""):
    assert_staff()
    return forms.approve(name, note)


@frappe.whitelist(methods=["POST"])
def send_back(name, note):
    assert_staff()
    return forms.send_back(name, note)


@frappe.whitelist(methods=["POST"])
def discard(name):
    assert_staff()
    return forms.discard(name)


@frappe.whitelist(methods=["POST"])
def attach(name, content, filename=""):
    assert_staff()
    return forms.attach(name, content, filename)


@frappe.whitelist()
def list_forms(project=None, task=None, state=None, template_code=None, start=0, limit=50):
    assert_staff()
    return forms.list_forms(project or None, task or None, state or None, template_code or None, start, limit)


@frappe.whitelist()
def waiting_for_me(limit=20):
    assert_staff()
    return forms.waiting_for_me(limit)


@frappe.whitelist()
def for_task(task):
    assert_staff()
    return forms.for_task(task)


@frappe.whitelist()
def pdf(name):
    assert_staff()
    filename, content = form_output.pdf_of(name)
    _file(filename, content)


@frappe.whitelist()
def export(project, template_code):
    assert_staff()
    filename, content = form_output.export_xlsx(project, template_code)
    _file(filename, content, "binary")


# --- requirements on tasks ----------------------------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def gate_add(task, form_code, note=""):
    assert_staff()
    return gates.add(task, form_code, note)


@frappe.whitelist(methods=["POST"])
def gate_remove(name):
    assert_staff()
    return gates.remove(name)
