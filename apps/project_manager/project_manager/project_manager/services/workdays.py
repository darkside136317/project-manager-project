"""Working days of a project, from its Holiday List: turning dates into day numbers the schedule can add up, and back.

The list covers a limited period (usually a fiscal year). Beyond it the weekly days off still apply; public holidays are
only known for the years someone entered.
"""

from bisect import bisect_left
from datetime import date, timedelta

import frappe
from frappe.utils import getdate

FIRST = date(2000, 1, 1)
LAST = date(2080, 12, 31)
DEFAULT_WEEKLY_OFF = frozenset({6})  # Sunday, when no list says otherwise


class WorkCalendar:
    def __init__(self, holidays=(), weekly_off=DEFAULT_WEEKLY_OFF):
        self.holidays = {getdate(d) for d in holidays}
        self.weekly_off = frozenset(weekly_off)
        days = []
        day, one = FIRST, timedelta(days=1)
        while day <= LAST:
            if day.weekday() not in self.weekly_off and day not in self.holidays:
                days.append(day)
            day += one
        self.days = days

    def is_working(self, day) -> bool:
        day = getdate(day)
        return day.weekday() not in self.weekly_off and day not in self.holidays

    def index(self, day, forward: bool = True) -> int:
        """Number of a working day. A day off gives the next working day (or the previous one with forward=False)."""
        day = getdate(day)
        position = bisect_left(self.days, day)
        if position < len(self.days) and self.days[position] == day:
            return position
        return position if forward else position - 1

    def date_at(self, position: int) -> date:
        return self.days[max(0, min(position, len(self.days) - 1))]

    def count(self, first, last) -> int:
        """Working days from `first` to `last`, both included (0 if the period holds none)."""
        return max(0, self.index(last, forward=False) - self.index(first, forward=True) + 1)

    def between(self, first, last) -> list[str]:
        """The days off in a period, as ISO dates (the Gantt shades them)."""
        first, last = getdate(first), getdate(last)
        out, day, one = [], first, timedelta(days=1)
        while day <= last:
            if not self.is_working(day):
                out.append(day.isoformat())
            day += one
        return out


def list_of(project: str | None) -> str | None:
    """The Holiday List of a project: its own, else its company's."""
    if not project:
        return None
    info = frappe.db.get_value("Project", project, ["pm_holiday_list", "company"], as_dict=True)
    if not info:
        return None
    return info.pm_holiday_list or frappe.db.get_value("Company", info.company, "default_holiday_list")


def _weekly_off(rows) -> frozenset:
    """The weekdays a list marks as weekly days off."""
    days = {getdate(row.holiday_date).weekday() for row in rows if row.weekly_off}
    return frozenset(days) if days else DEFAULT_WEEKLY_OFF


def calendar_of(project: str | None) -> WorkCalendar:
    """The calendar of a project, built once per request for each Holiday List."""
    return calendar_named(list_of(project))


def calendars_of(projects) -> dict:
    """{project: calendar} for many projects with two queries (the portfolio)."""
    projects = list(projects)
    if not projects:
        return {}
    rows = frappe.get_all("Project", filters={"name": ["in", projects]}, fields=["name", "pm_holiday_list", "company"],
                          limit_page_length=0)
    companies = list({r.company for r in rows if not r.pm_holiday_list and r.company})
    lists = dict(frappe.get_all("Company", filters={"name": ["in", companies]}, fields=["name", "default_holiday_list"],
                                as_list=True)) if companies else {}
    return {r.name: calendar_named(r.pm_holiday_list or lists.get(r.company)) for r in rows}


def calendar_named(name: str | None) -> WorkCalendar:
    """The calendar of a Holiday List (None: only the default weekly day off), built once per request."""
    memo = getattr(frappe.local, "pm_calendars", None)
    if memo is None:
        memo = frappe.local.pm_calendars = {}
    if name not in memo:
        rows = frappe.get_all("Holiday", filters={"parent": name, "parenttype": "Holiday List"},
                              fields=["holiday_date", "weekly_off"], limit_page_length=0) if name else []
        memo[name] = WorkCalendar((row.holiday_date for row in rows), _weekly_off(rows))
    return memo[name]
