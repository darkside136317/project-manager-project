"""M4: the critical path on small examples worked out by hand, and the calendar it counts in. No database involved.

Run: bench --site <site> run-tests --app project_manager --module project_manager.tests.test_cpm
"""

import unittest
from datetime import date

from project_manager.project_manager.services.cpm import FF, FS, SF, SS, Activity, CycleError, Link, forward, order, solve
from project_manager.project_manager.services.workdays import WorkCalendar


def network(**durations):
    return {key: Activity(duration) for key, duration in durations.items()}


class TestCriticalPath(unittest.TestCase):
    def test_a_chain_is_all_critical(self):
        result = solve(network(a=3, b=2, c=4), [Link("a", "b", FS, 0), Link("b", "c", FS, 0)])
        self.assertEqual((result.start, result.finish), ({"a": 0, "b": 3, "c": 5}, {"a": 3, "b": 5, "c": 9}))
        self.assertEqual(result.end, 9)
        self.assertEqual(set(result.total_float.values()), {0})

    def test_the_short_branch_has_float(self):
        #      /-- b (5) --\
        # a(2)              d(1)
        #      \-- c (2) --/
        links = [Link("a", "b", FS, 0), Link("a", "c", FS, 0), Link("b", "d", FS, 0), Link("c", "d", FS, 0)]
        result = solve(network(a=2, b=5, c=2, d=1), links)
        self.assertEqual(result.end, 8)
        self.assertEqual(result.total_float, {"a": 0, "b": 0, "c": 3, "d": 0})
        self.assertEqual((result.late_start["c"], result.late_finish["c"]), (5, 7))

    def test_every_kind_of_link(self):
        # a occupies 2..6; b lasts 3 and, untied, would start at 2 (the earliest point of the network)
        cases = (
            (FS, 0, 6, 9), (FS, 2, 8, 11), (FS, -1, 5, 8),
            (SS, 0, 2, 5), (SS, 3, 5, 8),
            (FF, 0, 3, 6), (FF, 2, 5, 8),
            (SF, 0, 2, 5), (SF, 5, 4, 7),
        )
        for kind, lag, start, finish in cases:
            activities = {"a": Activity(4, not_before=2), "b": Activity(3)}
            got_start, got_finish = forward(activities, [Link("a", "b", kind, lag)])
            self.assertEqual((got_start["b"], got_finish["b"]), (start, finish), f"{kind}{lag:+d}")

    def test_the_backward_pass_follows_every_kind_of_link(self):
        # a (2 days) and c (10 days) both may start at 0; how they are tied decides the end and a's room to slip
        cases = (
            (FS, 0, 0, 12),   # c waits for a: nothing to spare
            (SS, 0, 0, 10),   # a must start before c may, and c has no room
            (FF, 0, 8, 10),   # a only has to finish before c does
            (FF, -3, 8, 10),  # looser still, but the end of the network caps it
            (SF, 12, 0, 12),  # c's finish is pushed by a's start
            (SF, 5, 5, 10),   # a may start as late as c's finish minus 5
        )
        for kind, lag, spare, end in cases:
            activities = {"a": Activity(2, not_before=0), "c": Activity(10, not_before=0)}
            result = solve(activities, [Link("a", "c", kind, lag)])
            self.assertEqual((result.total_float["a"], result.end), (spare, end), f"{kind}{lag:+d}")

    def test_a_planned_start_holds_and_leaves_float_behind_it(self):
        activities = {"a": Activity(2, not_before=0), "b": Activity(2, not_before=10)}
        result = solve(activities, [Link("a", "b", FS, 0)])
        self.assertEqual(result.start["b"], 10)  # planned later than a allows: the plan stands
        self.assertEqual(result.total_float, {"a": 8, "b": 0})

    def test_a_link_pushes_a_plan_that_ignores_it(self):
        activities = {"a": Activity(5, not_before=0), "b": Activity(2, not_before=1)}
        start, finish = forward(activities, [Link("a", "b", FS, 0)])
        self.assertEqual((start["b"], finish["b"]), (5, 7))

    def test_what_is_done_is_done(self):
        activities = {"a": Activity(5, not_before=0), "b": Activity(3, fixed_start=2, fixed_finish=4), "c": Activity(1)}
        start, finish = forward(activities, [Link("a", "b", FS, 0), Link("b", "c", FS, 0)])
        self.assertEqual((start["b"], finish["b"]), (2, 4))  # a's dates no longer matter to it
        self.assertEqual(start["c"], 4)

    def test_work_under_way_stretches(self):
        activities = {"a": Activity(4, fixed_start=0, min_finish=9), "b": Activity(1)}
        start, finish = forward(activities, [Link("a", "b", FS, 0)])
        self.assertEqual((start["a"], finish["a"], start["b"]), (0, 9, 9))
        # a late predecessor stretches the finish, never the start
        activities = {"p": Activity(12, not_before=0), "a": Activity(4, fixed_start=0)}
        start, finish = forward(activities, [Link("p", "a", FF, 0)])
        self.assertEqual((start["a"], finish["a"]), (0, 12))
        activities = {"p": Activity(12, not_before=0), "a": Activity(4, fixed_start=0)}
        self.assertEqual(forward(activities, [Link("p", "a", FS, 0)])[0]["a"], 0)

    def test_a_milestone_takes_no_time(self):
        result = solve(network(a=3, m=0, b=2), [Link("a", "m", FS, 0), Link("m", "b", FS, 0)])
        self.assertEqual((result.start["m"], result.finish["m"], result.start["b"]), (3, 3, 3))
        self.assertEqual(result.total_float["m"], 0)

    def test_circles_are_found_at_any_length(self):
        length = 40  # ERPNext's own check gives up after 15 steps
        keys = [f"t{i}" for i in range(length)]
        links = [Link(keys[i], keys[i + 1], FS, 0) for i in range(length - 1)]
        activities = network(**dict.fromkeys(keys, 1), free=1)
        self.assertEqual(len(order(activities, links)), length + 1)
        with self.assertRaises(CycleError) as caught:
            order(activities, [*links, Link(keys[-1], keys[0], FS, 0)])
        self.assertEqual(set(caught.exception.nodes), set(keys))

    def test_nothing_to_do(self):
        result = solve({}, [])
        self.assertEqual((result.end, result.total_float), (0, {}))

    def test_a_large_network_is_quick(self):
        import time

        size = 20000
        activities = {i: Activity(1 + i % 7, not_before=i % 300) for i in range(size)}
        links = [Link(i, i + 1, FS, 0) for i in range(0, size - 1, 2)] + [Link(i, i + 500, SS, 1) for i in range(0, size - 500, 10)]
        started = time.perf_counter()
        solve(activities, links)
        self.assertLess(time.perf_counter() - started, 2.0)


class TestWorkCalendar(unittest.TestCase):
    def setUp(self):
        # 1 Jan 2026 is a Thursday; Sundays off, and one public holiday on Friday 2 Jan
        self.calendar = WorkCalendar([date(2026, 1, 2)], {6})

    def test_days_off(self):
        self.assertFalse(self.calendar.is_working("2026-01-02"))
        self.assertFalse(self.calendar.is_working("2026-01-04"))  # Sunday
        self.assertTrue(self.calendar.is_working("2026-01-03"))

    def test_counting(self):
        self.assertEqual(self.calendar.count("2026-01-01", "2026-01-05"), 3)  # Thu, Sat, Mon
        self.assertEqual(self.calendar.count("2026-01-02", "2026-01-02"), 0)
        self.assertEqual(self.calendar.count("2026-01-03", "2026-01-03"), 1)

    def test_numbers_and_back(self):
        first = self.calendar.index("2026-01-01")
        self.assertEqual(self.calendar.index("2026-01-02"), first + 1)  # a day off moves on to the next working day
        self.assertEqual(self.calendar.index("2026-01-02", forward=False), first)  # or back to the previous one
        self.assertEqual(self.calendar.date_at(first + 1), date(2026, 1, 3))
        self.assertEqual(self.calendar.date_at(self.calendar.index("2026-01-05")), date(2026, 1, 5))

    def test_days_off_of_a_period(self):
        self.assertEqual(self.calendar.between("2026-01-01", "2026-01-05"), ["2026-01-02", "2026-01-04"])

    def test_the_weekly_pattern_goes_on_beyond_the_list(self):
        self.assertFalse(self.calendar.is_working("2031-06-01"))  # a Sunday, years after the list
