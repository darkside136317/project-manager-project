"""Background jobs that work through a "dirty" set (the roll-up, the critical path of a project).

Frappe's `deduplicate` skips a job whose id is queued *or running*. A running job may already have taken its last look
at the dirty set: what was marked meanwhile would then wait for the 5-minute sweeper. So when the job is running, one
follow-up job is queued under a second id; it runs right after and picks up what is left.
"""

import frappe


def enqueue_once(method: str, job_id: str, queue: str, **kwargs) -> None:
    from frappe.utils.background_jobs import get_job_status
    from rq.job import JobStatus

    try:
        running = get_job_status(job_id) == JobStatus.STARTED
    except Exception:
        running = False  # Redis unreachable: the plain deduplicated job, the sweeper catches up
    frappe.enqueue(method, queue=queue, job_id=f"{job_id}:next" if running else job_id, deduplicate=True, **kwargs)
