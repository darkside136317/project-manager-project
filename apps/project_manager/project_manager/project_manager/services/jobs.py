"""Background jobs that work through a "dirty" set (the roll-up, the critical path of a project).

Frappe's `deduplicate` skips a job whose id is queued *or running*. A running job may already have taken its last look
at the dirty set: what was marked meanwhile would then wait for the 5-minute sweeper. So when the job is running, one
follow-up job is queued under a second id; it runs right after and picks up what is left.

enqueue_once runs after the commit (the change is saved): it never raises. Under load (M11, 200 people reporting at
once) Frappe's re-queue of a job that has just finished can fail in RQ ("Execution ... not found in Redis") while the
worker cleans it up: that turned saved reports into error pages. Such a failure is tried once more, then left to the
sweeper, which finds the dirty set intact. A job already waiting is not handed to frappe.enqueue at all, which would log
an error line for every skipped duplicate.
"""

import frappe

WAITING = ("queued", "scheduled", "deferred")


def enqueue_once(method: str, job_id: str, queue: str, **kwargs) -> None:
    from frappe.utils.background_jobs import get_job_status

    for attempt in (1, 2):
        try:
            status = _value(get_job_status(job_id))
            if status in WAITING:
                return  # it has not started: it will see what was just marked
            target = job_id
            if status == "started":
                target = f"{job_id}:next"
                if _value(get_job_status(target)) in WAITING:
                    return
            frappe.enqueue(method, queue=queue, job_id=target, deduplicate=True, **kwargs)
            return
        except Exception as error:
            if attempt == 2:
                frappe.logger("project_manager").warning(
                    f"enqueue {job_id} failed ({type(error).__name__}: {error}); the sweeper will pick it up")


def _value(status) -> str | None:
    """RQ's JobStatus (an enum of strings) or None, as a plain string."""
    return getattr(status, "value", status)
