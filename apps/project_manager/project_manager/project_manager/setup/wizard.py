"""ERPNext setup wizard driven by docker/.env, so a fresh clone needs no clicks in the browser.

Run by the `setup-site` one-shot service on every bootstrap:

    bench --site <site> execute project_manager.project_manager.setup.wizard.ensure_setup

Every step is idempotent: a site that is already set up only gets what is missing.
"""

import os

import frappe
from frappe.utils import add_days, add_years, getdate, nowdate

DEFAULTS = {
    "COMPANY_NAME": "Công ty Xây dựng Mẫu",
    "COMPANY_ABBR": "CTXD",
    "COUNTRY": "Vietnam",
    "CURRENCY": "VND",
    "TIMEZONE": "Asia/Ho_Chi_Minh",
    "LANGUAGE": "vi",
    "FY_START": "01-01",
    "WEEKLY_OFF": "Sunday",
}


def env(key: str) -> str:
    return (os.environ.get(key) or DEFAULTS[key]).strip()


def ensure_setup():
    """Complete the setup wizard (company, fiscal year, defaults) and the company's holiday list."""
    if not frappe.is_setup_complete():
        run_wizard()
    company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
    ensure_holiday_list(company)
    frappe.db.commit()
    print(f"Setup complete: company {company!r}, holiday list {frappe.db.get_value('Company', company, 'default_holiday_list')!r}")


def run_wizard():
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    start, end = fiscal_year_dates(env("FY_START"))
    language = frappe.db.get_value("Language", env("LANGUAGE"), "language_name") or "English"
    setup_complete({
        # Frappe stage. No email: the wizard would create a second System Manager.
        "language": language,
        "lang": language,
        "country": env("COUNTRY"),
        "timezone": env("TIMEZONE"),
        "currency": env("CURRENCY"),
        "enable_telemetry": 0,
        # ERPNext stage
        "company_name": env("COMPANY_NAME"),
        "company_abbr": env("COMPANY_ABBR"),
        "chart_of_accounts": "Standard",
        "fy_start_date": str(start),
        "fy_end_date": str(end),
    })


def fiscal_year_dates(fy_start: str, today=None):
    """(start, end) of the fiscal year containing today, for a start given as MM-DD."""
    today = getdate(today or nowdate())
    month, day = (int(part) for part in fy_start.split("-"))
    start = getdate(f"{today.year}-{month:02d}-{day:02d}")
    if start > today:
        start = add_years(start, -1)
    return start, add_days(add_years(start, 1), -1)


def ensure_holiday_list(company: str):
    """Weekly days off plus the country's public holidays for the current fiscal year, as the company default."""
    if not company or frappe.db.get_value("Company", company, "default_holiday_list"):
        return
    start, end = fiscal_year_dates(env("FY_START"))
    name = f"{frappe.db.get_value('Company', company, 'abbr')} {start.year}"
    if not frappe.db.exists("Holiday List", name):
        holidays = frappe.new_doc("Holiday List")
        holidays.update({
            "holiday_list_name": name,
            "from_date": start,
            "to_date": end,
            "weekly_off": env("WEEKLY_OFF"),
            "country": (frappe.db.get_value("Country", env("COUNTRY"), "code") or "").upper() or None,
        })
        holidays.get_weekly_off_dates()
        if holidays.country:
            # Holiday names in the site language (the wizard may have just changed it).
            frappe.local.lang = frappe.db.get_single_value("System Settings", "language") or "en"
            try:
                holidays.get_local_holidays()
            except NotImplementedError:
                pass  # the holidays library does not know this country: weekly days off only
        holidays.insert(ignore_permissions=True)
    frappe.db.set_value("Company", company, "default_holiday_list", name)
