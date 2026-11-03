"""Position of a task in its project's tree (WBS), kept per project.

Frappe's nested set renumbers `lft/rgt` of the WHOLE Task table on every insert (`UPDATE tabTask SET rgt = rgt + 2
WHERE rgt >= ...`): with a million tasks one insert locks rows of every project. The Task mixin turns that off and
this module keeps a materialised path instead, local to one project:

    pm_sort      position among its siblings (1, 2, 3 ...; gaps are fine, the order is what matters)
    pm_path      the sort keys from the root, fixed width: "00001.00003.00002" (string order = tree order)
    pm_level     depth, 1 for a root task of the project
    pm_wbs_code  the same path for people: "1.3.2"

A new task takes the next position under its parent; moving a task (new parent or project) rewrites the paths of
its subtree with one UPDATE limited to the project. `lft`/`rgt` stay 0 and nothing reads them.
"""

import frappe
from frappe import _
from frappe.utils import cint

WIDTH = 5
MAX_SIBLINGS = 10**WIDTH - 1


def segment(sort: int) -> str:
    return f"{int(sort):0{WIDTH}d}"


def _lock_and_next_sort(project: str | None, parent: str | None, exclude: str | None) -> int:
    """Next free position under `parent` (or among the project's roots), with the parent (or project) row locked so
    two tasks added at the same time do not take the same position."""
    values = {"parent": parent, "project": project, "exclude": exclude or ""}
    if parent:
        frappe.db.sql("select name from `tabTask` where name = %s for update", parent)
        where = "parent_task = %(parent)s"
    else:
        if project:
            frappe.db.sql("select name from `tabProject` where name = %s for update", project)
        where = ("project = %(project)s" if project else "ifnull(project, '') = ''") + " and ifnull(parent_task, '') = ''"
    current = frappe.db.sql(f"select max(pm_sort) from `tabTask` where {where} and name != %(exclude)s", values)[0][0]
    value = cint(current) + 1
    if value > MAX_SIBLINGS:
        frappe.throw(_("Một nút không thể có quá {0} việc con").format(MAX_SIBLINGS))
    return value


def place(doc) -> None:
    """Before saving a task: give it a position when it is new or has moved (other parent or project)."""
    before = None if doc.is_new() else frappe.db.get_value(
        "Task", doc.name, ["project", "parent_task", "pm_path", "pm_wbs_code", "pm_level"], as_dict=True)
    moved = before is not None and ((before.project or None) != (doc.project or None)
                                    or (before.parent_task or None) != (doc.parent_task or None))
    if before is not None and not moved and before.pm_path:
        return
    parent = None
    if doc.parent_task:
        if doc.parent_task == doc.name:
            frappe.throw(_("Công việc không thể là việc cha của chính nó"))
        parent = frappe.db.get_value("Task", doc.parent_task, ["project", "pm_path", "pm_wbs_code", "pm_level"], as_dict=True)
        if not parent:
            frappe.throw(_("Không tìm thấy việc cha {0}").format(doc.parent_task))
        if (parent.project or None) != (doc.project or None):
            frappe.throw(_("Việc cha {0} thuộc dự án khác").format(doc.parent_task))
        if before is not None and before.pm_path and parent.pm_path and (
                parent.pm_path == before.pm_path or parent.pm_path.startswith(before.pm_path + ".")):
            frappe.throw(_("Không thể chuyển công việc vào bên trong chính nhánh của nó"))
    sort = _lock_and_next_sort(doc.project, doc.parent_task, None if doc.is_new() else doc.name)
    doc.pm_sort = sort
    if parent:
        doc.pm_path = f"{parent.pm_path}.{segment(sort)}" if parent.pm_path else segment(sort)
        doc.pm_wbs_code = f"{parent.pm_wbs_code}.{sort}" if parent.pm_wbs_code else str(sort)
        doc.pm_level = cint(parent.pm_level) + 1 if parent.pm_level else 1
    else:
        doc.pm_path, doc.pm_wbs_code, doc.pm_level = segment(sort), str(sort), 1
    if moved:
        doc.flags.pm_moved_from = before


def carry_subtree(doc) -> int:
    """After saving a moved task: its descendants follow it (path, code, level, project). Returns rows updated."""
    before = doc.flags.pop("pm_moved_from", None)
    if not before or not before.pm_path:
        return 0
    frappe.db.sql(
        """update `tabTask`
           set pm_path = concat(%(path)s, substring(pm_path, %(cut_path)s)),
               pm_wbs_code = concat(%(code)s, substring(pm_wbs_code, %(cut_code)s)),
               pm_level = pm_level + %(delta)s,
               project = %(project)s
           where ifnull(project, '') = %(old_project)s and pm_path like %(prefix)s""",
        {"path": doc.pm_path, "cut_path": len(before.pm_path) + 1, "code": doc.pm_wbs_code,
         "cut_code": len(before.pm_wbs_code or "") + 1, "delta": cint(doc.pm_level) - cint(before.pm_level),
         "project": doc.project, "old_project": before.project or "",
         "prefix": before.pm_path.replace("%", r"\%").replace("_", r"\_") + ".%"})
    return frappe.db.sql("select row_count()")[0][0] or 0


def rebuild(project: str) -> int:
    """Number the whole tree of a project again (1, 2, 3 ... in the current order). Returns the number of tasks."""
    rows = frappe.get_all("Task", filters={"project": project},
                          fields=["name", "parent_task", "pm_sort", "creation"], limit_page_length=0)
    children = {}
    for row in rows:
        children.setdefault(row.parent_task or None, []).append(row)
    names = {row.name for row in rows}
    roots = [r for parent, kids in children.items() if parent is None or parent not in names for r in kids]
    updates = []

    def walk(nodes, path, code, level):
        nodes.sort(key=lambda r: (cint(r.pm_sort) or MAX_SIBLINGS, r.creation, r.name))
        for i, node in enumerate(nodes, 1):
            own_path = f"{path}.{segment(i)}" if path else segment(i)
            own_code = f"{code}.{i}" if code else str(i)
            updates.append((i, own_path, own_code, level, node.name))
            walk(children.get(node.name, []), own_path, own_code, level + 1)

    walk(roots, "", "", 1)
    for chunk in range(0, len(updates), 500):
        batch = updates[chunk:chunk + 500]
        frappe.db.sql(
            "update `tabTask` set pm_sort = case name {s} end, pm_path = case name {p} end, pm_wbs_code = case name {c} end,"
            " pm_level = case name {l} end where name in ({names})".format(
                s=" ".join(f"when {frappe.db.escape(u[4])} then {u[0]}" for u in batch),
                p=" ".join(f"when {frappe.db.escape(u[4])} then {frappe.db.escape(u[1])}" for u in batch),
                c=" ".join(f"when {frappe.db.escape(u[4])} then {frappe.db.escape(u[2])}" for u in batch),
                l=" ".join(f"when {frappe.db.escape(u[4])} then {u[3]}" for u in batch),
                names=", ".join(frappe.db.escape(u[4]) for u in batch)))
    return len(updates)
