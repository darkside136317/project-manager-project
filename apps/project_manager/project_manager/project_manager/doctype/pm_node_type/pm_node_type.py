import frappe
from frappe import _
from frappe.model.document import Document


class PMNodeType(Document):
    """Loại nút của cây công việc (WBS): Giai đoạn, Nhóm việc, Công việc, Mốc... Layers add their own (fixtures)."""

    def validate(self):
        self.node_type = (self.node_type or "").strip()
        if self.is_group and not self.counts_in_rollup:
            frappe.throw(_("Nút nhóm luôn được tính vào tiến độ (tiến độ của nó là tổng hợp từ việc con)"))

    def on_trash(self):
        if self.is_builtin and not frappe.flags.in_uninstall:
            frappe.throw(_("Không xóa được loại nút có sẵn"))
        if frappe.db.exists("Task", {"pm_node_type": self.name}):
            frappe.throw(_("Loại nút {0} đang được dùng").format(self.name))
