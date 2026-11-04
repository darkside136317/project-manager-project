"""ERPNext's Task, adapted to large multi-project use without touching ERPNext's code.

Registered through the `extend_doctype_class` hook: this mixin comes before ERPNext's Task in the method resolution
order, so each method here replaces ERPNext's (and calls it through super() where part of it is kept). Every method
overridden here is listed in OVERRIDDEN; tests/test_task_mixin.py checks that ERPNext still has each of them, so an
ERPNext upgrade that renames one fails the tests instead of silently bringing the old behaviour back.

What changes, and why:

* update_nsm_model     Frappe's nested set renumbers the whole Task table on every insert; the tree is kept per
                       project in pm_path / pm_wbs_code / pm_level instead (services/wbs.py).
* populate_depends_on  ERPNext adds every child to its parent's "depends on" table and saves the parent, which
                       cascades saves up the tree. Dependencies live in our own table (M4); hierarchy is not one.
* check_recursion      Walks ERPNext's dependency table (empty here) and gives up after 15 steps.
* reschedule_dependent_tasks  Never effective in v16 (it filters on a column nothing fills); scheduling is ours (M4).
* update_project       Recounted every task of the project and saved a possibly stale cached Project on every task
                       save (and after a delete). Here it only marks the parent for the incremental roll-up, which
                       runs after the commit on the "pm" queue (services/rollup.py).
* validate_parent_expected_end_date / validate_parent_project_dates
                       Refused a late task (an actual date after the project's planned end) or a child ending after its
                       parent. Late work must be recordable; dates of group tasks will come from roll-up (M2/M4).
* update_status        Called by ERPNext's daily job to overwrite the status with "Overdue"; that job is stopped
                       (setup/install.py) and lateness is a separate flag (pm_is_overdue / pm_delay_days, set here
                       on save and refreshed daily), never the status.
* validate             While a Timesheet is being submitted or cancelled ERPNext forces the status of its tasks to
                       Completed / Working; the status and progress the team set are kept (hooks: Timesheet events).
                       A leaf's roll-up weight and its lateness are computed here too, and a move to Completed is
                       refused while a required form is not approved (services/gates.py).
"""

import frappe
from frappe.utils import flt

from project_manager.project_manager.services import gates, rollup, wbs

OVERRIDDEN = (
    "validate", "update_nsm_model", "populate_depends_on", "check_recursion", "reschedule_dependent_tasks",
    "update_project", "validate_parent_expected_end_date", "validate_parent_project_dates", "update_status",
)
TIMESHEET_FLAG = "pm_timesheet_sync"


class PMTaskMixin:
    def validate(self):
        if frappe.flags.get(TIMESHEET_FLAG) and not self.is_new():
            kept = frappe.db.get_value("Task", self.name, ["status", "progress"], as_dict=True)
            if kept:
                self.status, self.progress = kept.status, flt(kept.progress)
        super().validate()
        if not self.is_group and self.project:
            self.pm_rollup_weight = rollup.leaf_weight(self, rollup.method_of(self.project))
        self.pm_is_overdue, self.pm_delay_days = rollup.overdue_state(self)
        gates.check_close(self)

    def before_save(self):
        parent = getattr(super(), "before_save", None)
        if parent:
            parent()
        wbs.place(self)

    def update_nsm_model(self):
        wbs.carry_subtree(self)
        if (self.get("old_parent") or "") != (self.parent_task or ""):
            self.db_set("old_parent", self.parent_task or "", update_modified=False)

    def populate_depends_on(self):
        pass

    def check_recursion(self):
        pass

    def reschedule_dependent_tasks(self):
        pass

    def update_project(self):
        # on_update and after_delete
        if rollup.changed(self):
            rollup.mark_dirty(self)

    def validate_parent_expected_end_date(self):
        pass

    def validate_parent_project_dates(self):
        pass

    def update_status(self):
        pass


def timesheet_started(doc, method=None):
    """Timesheet before_submit / before_cancel: ERPNext is about to save the timesheet's tasks."""
    frappe.flags[TIMESHEET_FLAG] = True


def timesheet_finished(doc, method=None):
    """Timesheet on_submit / on_cancel (after ERPNext's own handler): back to normal."""
    frappe.flags[TIMESHEET_FLAG] = False
