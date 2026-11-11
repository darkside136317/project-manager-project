from frappe.model.document import Document


class PMCWorker(Document):
    """Công nhân (seasonal workers are not users of the app): a crew (PM Team), a trade, a daily rate. The ID number is
    at permission level 1 (administrators only)."""

    def validate(self):
        self.full_name = " ".join((self.full_name or "").split())
