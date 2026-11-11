from frappe.model.document import Document


class PMNotificationPreference(Document):
    """A person's own choices about notices (services/alerts.py): email, quiet hours, digests, muted alert types."""
