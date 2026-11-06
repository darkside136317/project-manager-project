"""The critical path method on plain numbers: no database, no dates, so it can be tested with small examples.

Time is counted in working days as points between days: an activity of 3 days starting at point 10 finishes at point 13
(it occupies days 10, 11, 12). A milestone has duration 0. A link says how the successor is tied to the predecessor,
lag in working days (negative: overlap):

    FS  successor's start  >= predecessor's finish + lag
    SS  successor's start  >= predecessor's start  + lag
    FF  successor's finish >= predecessor's finish + lag
    SF  successor's finish >= predecessor's start  + lag

An activity may also carry:

    not_before    it does not start earlier than this, even if its predecessors would allow it (its planned start)
    fixed_start   it did start then: links can no longer change its start
    fixed_finish  it did finish then: links can no longer change anything about it
    min_finish    it cannot finish earlier than this (what is left of work under way)

A plain activity keeps its duration: pushing its finish moves its start. A started one is stretched instead.
"""

from collections import deque, namedtuple

FS, SS, FF, SF = "FS", "SS", "FF", "SF"
LINK_TYPES = (FS, SS, FF, SF)

Link = namedtuple("Link", "pred succ kind lag")
Schedule = namedtuple("Schedule", "start finish late_start late_finish total_float end")


class Activity:
    __slots__ = ("duration", "not_before", "fixed_start", "fixed_finish", "min_finish")

    def __init__(self, duration=0, not_before=None, fixed_start=None, fixed_finish=None, min_finish=None):
        self.duration = duration
        self.not_before = not_before
        self.fixed_start = fixed_start
        self.fixed_finish = fixed_finish
        self.min_finish = min_finish


class CycleError(ValueError):
    """The links go round in a circle. `nodes` are the activities caught in it."""

    def __init__(self, nodes):
        super().__init__(f"Phụ thuộc vòng tròn: {sorted(map(str, nodes))}")
        self.nodes = nodes


def order(activities, links) -> list:
    """Activities with every predecessor before its successors (Kahn). Raises CycleError."""
    waiting = dict.fromkeys(activities, 0)
    following = {key: [] for key in activities}
    for link in links:
        waiting[link.succ] += 1
        following[link.pred].append(link.succ)
    queue = deque(key for key, count in waiting.items() if count == 0)
    out = []
    while queue:
        key = queue.popleft()
        out.append(key)
        for succ in following[key]:
            waiting[succ] -= 1
            if waiting[succ] == 0:
                queue.append(succ)
    if len(out) != len(waiting):
        raise CycleError([key for key, count in waiting.items() if count > 0])
    return out


def _incoming(links) -> dict:
    out = {}
    for link in links:
        out.setdefault(link.succ, []).append(link)
    return out


def forward(activities, links, sequence=None, origin=None) -> tuple[dict, dict]:
    """Earliest start and finish of every activity."""
    sequence = sequence if sequence is not None else order(activities, links)
    incoming = _incoming(links)
    if origin is None:
        floors = [a.not_before for a in activities.values() if a.not_before is not None]
        floors += [a.fixed_start for a in activities.values() if a.fixed_start is not None]
        origin = min(floors, default=0)
    start, finish = {}, {}
    for key in sequence:
        activity = activities[key]
        if activity.fixed_finish is not None:
            finish[key] = activity.fixed_finish
            start[key] = activity.fixed_start if activity.fixed_start is not None else activity.fixed_finish - activity.duration
            continue
        earliest = activity.fixed_start if activity.fixed_start is not None else (
            activity.not_before if activity.not_before is not None else origin)
        finish_floor = activity.min_finish
        for link in incoming.get(key, ()):
            if link.kind == FS or link.kind == SS:
                if activity.fixed_start is None:
                    value = (finish[link.pred] if link.kind == FS else start[link.pred]) + link.lag
                    earliest = max(earliest, value)
            else:
                value = (finish[link.pred] if link.kind == FF else start[link.pred]) + link.lag
                finish_floor = value if finish_floor is None else max(finish_floor, value)
        end = earliest + activity.duration
        if finish_floor is not None and finish_floor > end:
            end = finish_floor
            if activity.fixed_start is None:
                earliest = end - activity.duration
        start[key], finish[key] = earliest, end
    return start, finish


def solve(activities, links) -> Schedule:
    """Forward and backward pass. Total float is measured against the end of the whole network: an activity with no
    float left cannot slip without moving that end, which is what makes it critical."""
    sequence = order(activities, links)
    start, finish = forward(activities, links, sequence)
    end = max(finish.values(), default=0)
    outgoing = {}
    for link in links:
        outgoing.setdefault(link.pred, []).append(link)
    late_start, late_finish = {}, {}
    for key in reversed(sequence):
        duration = finish[key] - start[key]
        latest = end
        for link in outgoing.get(key, ()):
            if link.kind == FS:
                value = late_start[link.succ] - link.lag
            elif link.kind == SS:
                value = late_start[link.succ] - link.lag + duration
            elif link.kind == FF:
                value = late_finish[link.succ] - link.lag
            else:
                value = late_finish[link.succ] - link.lag + duration
            latest = min(latest, value)
        late_finish[key] = latest
        late_start[key] = latest - duration
    total_float = {key: late_start[key] - start[key] for key in sequence}
    return Schedule(start, finish, late_start, late_finish, total_float, end)
