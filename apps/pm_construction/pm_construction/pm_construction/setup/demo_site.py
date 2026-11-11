"""The site part of the factory demo (M8): materials and their norms, the site store, deliveries and issues to the
foundation (one material over its norm), a request waiting for the store keeper, machines (an owned excavator that is
an ERPNext Asset, a rented crane, a mixer) with their shifts, two crews and their attendance.

Quantities and prices are illustrative, not taken from any official norm book or price list. Called by setup/demo.py:
`masters()` before the BOQ is approved (so the material plan is built), `build()` after the diaries, `remove()` by
demo.down.
"""

import frappe
from frappe.utils import add_days, getdate

from pm_construction.pm_construction import constants as K
from pm_construction.pm_construction.services import costs, labour, machines, materials

MARK = "Dữ liệu mẫu (demo)"
KEEPER = ("demo.thukho@pm.localhost", "Đỗ Thủ Kho")
# code, name, uom, price
ITEMS = (
    ("VT-XM40", "Xi măng PCB40", "Kg", 1_850), ("VT-CATVANG", "Cát vàng", "m3", 380_000),
    ("VT-DA12", "Đá 1x2", "m3", 420_000), ("VT-DA46", "Đá 4x6", "m3", 390_000),
    ("VT-THEP18", "Thép tròn D18", "Kg", 17_500), ("VT-THEP10", "Thép tròn D10", "Kg", 17_800),
    ("VT-DAYBUOC", "Dây thép buộc", "Kg", 25_000), ("VT-GOVAN", "Gỗ ván khuôn", "m3", 6_500_000),
    ("VT-GACH", "Gạch đặc 6,5x10,5x22", "viên", 1_300), ("VT-CERAMIC", "Gạch ceramic 600x600", "m2", 165_000),
    ("VT-SON", "Sơn nước nội thất", "lít", 95_000),
)
CONCRETE_250 = (("VT-XM40", 350, 1), ("VT-CATVANG", 0.48, 2), ("VT-DA12", 0.9, 1))
# norm code, work, uom, [(item, per unit, waste %)]
NORMS = (
    ("AF.11111", "Bê tông lót móng đá 4x6, mác 100", "m3", (("VT-XM40", 200, 2), ("VT-CATVANG", 0.53, 2), ("VT-DA46", 0.94, 1))),
    ("AF.11223", "Bê tông móng đá 1x2, mác 250", "m3", CONCRETE_250),
    ("AF.12233", "Bê tông cột đá 1x2, mác 250", "m3", CONCRETE_250),
    ("AF.12313", "Bê tông dầm, sàn đá 1x2, mác 250", "m3", CONCRETE_250),
    ("AF.61120", "Cốt thép móng, đường kính ≤ 18 mm", "tấn", (("VT-THEP18", 1020, 0), ("VT-DAYBUOC", 14.28, 0))),
    ("AF.61432", "Cốt thép cột, đường kính ≤ 18 mm", "tấn", (("VT-THEP10", 1020, 0), ("VT-DAYBUOC", 14.28, 0))),
    ("AF.81111", "Ván khuôn móng băng", "100m2", (("VT-GOVAN", 0.79, 0),)),
    ("AE.22114", "Xây tường gạch đặc, vữa mác 75", "m3", (("VT-GACH", 550, 2), ("VT-XM40", 75, 1), ("VT-CATVANG", 0.3, 2))),
    ("AK.21224", "Trát tường trong, vữa mác 75", "m2", (("VT-XM40", 6.2, 1), ("VT-CATVANG", 0.019, 2))),
    ("AK.51250", "Lát nền gạch ceramic", "m2", (("VT-CERAMIC", 1.02, 0), ("VT-XM40", 8, 1))),
    ("AK.84114", "Sơn tường trong nhà", "m2", (("VT-SON", 0.35, 0),)),
)
DELIVERY = (("VT-XM40", 22_000), ("VT-CATVANG", 30), ("VT-DA12", 40), ("VT-DA46", 10), ("VT-THEP18", 4_500),
            ("VT-THEP10", 3_500), ("VT-DAYBUOC", 120), ("VT-GOVAN", 2))
# what each foundation work item got (index of the work item, item, quantity); the footing got 7 % more cement
ISSUES = ((1, "VT-XM40", 1_960), (1, "VT-CATVANG", 5.2), (1, "VT-DA46", 9.1),
          (2, "VT-THEP18", 4_350), (2, "VT-DAYBUOC", 61), (3, "VT-GOVAN", 1.05),
          (4, "VT-XM40", 14_600), (4, "VT-CATVANG", 19), (4, "VT-DA12", 35),
          (5, "VT-XM40", 1_400), (5, "VT-CATVANG", 1.9), (5, "VT-DA12", 3.5))
MACHINES = (("MX-01", "Máy đào bánh xích 0,8 m3", "Máy đào", K.OWNED, 2_600_000, 62),
            ("MT-01", "Máy trộn bê tông 250 lít", "Máy trộn", K.OWNED, 450_000, 0),
            ("CT-01", "Cần trục bánh hơi 16 tấn", "Cần trục", K.RENTED, 3_800_000, 45))
CREWS = (("Tổ nề Võ Tổ Trưởng", 0, (("Nguyễn Văn Lực", "Thợ nề", 450_000), ("Trần Văn Bền", "Thợ nề", 430_000),
                                     ("Lê Thị Hoa", "Phụ hồ", 350_000), ("Phạm Văn Sơn", "Phụ hồ", 350_000))),
         ("Tổ sắt", 1, (("Đặng Văn Thép", "Thợ sắt", 460_000), ("Bùi Văn Hàn", "Thợ hàn", 470_000),
                        ("Hồ Văn Cường", "Phụ", 360_000))))
ASSET_CATEGORY, ASSET_ITEM = "Máy thi công", "TS-MAYDAO"


def masters() -> None:
    """Materials and their norms (before the BOQ is approved)."""
    from pm_construction.pm_construction.setup import install

    install.ensure_stock_masters()
    for code, name, uom, _price in ITEMS:
        if not frappe.db.exists("Item", code):
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": K.ITEM_GROUP,
                            "stock_uom": uom, "is_stock_item": 1, "description": MARK}).insert(ignore_permissions=True)
    for code, work, uom, rows in NORMS:
        if not frappe.db.exists("PMC Material Norm", code):
            frappe.get_doc({"doctype": "PMC Material Norm", "norm_code": code, "description": work, "uom": uom, "note": MARK,
                            "materials": [{"item": i, "qty": q, "waste_pct": w} for i, q, w in rows]}).insert(
                ignore_permissions=True)


def _keeper(project) -> str:
    from project_manager.project_manager.services import projects

    email, name = KEEPER
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0,
                               "roles": [{"role": "PM Staff"}]})
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
    projects.add_member(project, email, "Thủ kho")
    return email


def build(project: str, works: list, today, people: dict, windows: list) -> None:
    keeper = _keeper(project)
    price = {code: p for code, _n, _u, p in ITEMS}
    frappe.set_user(keeper)
    materials.create_store(project)
    start = add_days(today, -18)
    materials.receive(project, [{"item": code, "qty": qty, "rate": price[code]} for code, qty in DELIVERY],
                      posting_date=start, note="Nhập vật tư đợt 1 (hóa đơn của nhà cung cấp)")
    for index, item, qty in ISSUES:
        if index < len(works):
            day = max(start, add_days(today, windows[index][0]))
            materials.issue(project, [{"task": works[index].name, "item": item, "qty": qty}], posting_date=day)
    materials.give_back(project, [{"task": works[4].name, "item": "VT-XM40", "qty": 150}],
                        posting_date=add_days(today, windows[4][1]), note="Xi măng thừa sau khi đổ móng")
    frappe.set_user(people["engineer"])
    materials.request(project, [{"task": works[6].name, "item": "VT-THEP10", "qty": 1_200},
                                {"task": works[6].name, "item": "VT-DAYBUOC", "qty": 18}],
                      note="Cốt thép cột trục 1–4", needed_by=add_days(today, 1))
    frappe.set_user("Administrator")
    _machines(project, works, today, people, windows)
    _crews(project, works, today, people, windows)
    frappe.set_user("Administrator")
    costs.refresh(project)


def _asset(company: str) -> str | None:
    """An owned excavator as an ERPNext Asset (left out if the company's asset accounts are not there)."""
    from pm_construction.pm_construction.setup.install import root_item_group

    try:
        if not frappe.db.exists("Asset Category", ASSET_CATEGORY):
            frappe.get_doc({"doctype": "Asset Category", "asset_category_name": ASSET_CATEGORY, "accounts": [{
                "company_name": company, "fixed_asset_account": materials.account_of(company, "Fixed Asset"),
                "accumulated_depreciation_account": materials.account_of(company, "Accumulated Depreciation"),
                "depreciation_expense_account": materials.account_of(company, "Depreciation")}]}).insert(
                ignore_permissions=True)
        if not frappe.db.exists("Item", ASSET_ITEM):
            frappe.get_doc({"doctype": "Item", "item_code": ASSET_ITEM, "item_name": "Máy đào bánh xích", "description": MARK,
                            "item_group": root_item_group(), "stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1,
                            "asset_category": ASSET_CATEGORY}).insert(ignore_permissions=True)
        asset = frappe.get_doc({"doctype": "Asset", "item_code": ASSET_ITEM, "asset_name": "Máy đào bánh xích 0,8 m3",
                                "company": company, "location": machines.site_location(None), "is_existing_asset": 1,
                                "asset_owner": "Company", "gross_purchase_amount": 1_850_000_000,
                                "purchase_amount": 1_850_000_000, "net_purchase_amount": 1_850_000_000,
                                "purchase_date": "2024-03-01", "available_for_use_date": "2024-03-01",
                                "calculate_depreciation": 0, "asset_category": ASSET_CATEGORY})
        asset.insert(ignore_permissions=True)
        asset.submit()
        return asset.name
    except Exception:
        frappe.log_error("Demo: tài sản máy đào", frappe.get_traceback())
        return None


def _machines(project, works, today, people, windows) -> None:
    company = materials.company_of(project)
    asset = _asset(company)
    for code, name, kind, ownership, rate, fuel in MACHINES:
        if frappe.db.exists("PMC Machine", code):
            continue
        frappe.get_doc({"doctype": "PMC Machine", "machine_code": code, "machine_name": name, "machine_type": kind,
                        "ownership": ownership, "asset": asset if code == "MX-01" else None, "shift_rate": rate,
                        "fuel_norm": fuel, "note": MARK,
                        "next_maintenance": add_days(today, 2) if code == "MX-01" else add_days(today, 40)}).insert(
            ignore_permissions=True)
        frappe.set_user(people["manager"])
        machines.transfer(code, project, add_days(today, -18), "Điều về công trường")
        frappe.set_user("Administrator")
    frappe.set_user(people["engineer"])
    for offset in range(-18, -14):  # digging the foundation
        if getdate(add_days(today, offset)).weekday() != 6:
            machines.record_shift(project, "MX-01", works[0].name, add_days(today, offset), 1, 8, 64, "Nguyễn Văn Máy")
    for index in (1, 4, 5):  # mixing the concrete
        first = windows[index][0]
        machines.record_shift(project, "MT-01", works[index].name, add_days(today, first), 1, 8, None, "Lê Văn Trộn")
    machines.record_shift(project, "CT-01", works[5].name, add_days(today, -5), 0.5, 4, 22, "Đơn vị cho thuê")
    frappe.set_user("Administrator")


def _crews(project, works, today, people, windows) -> None:
    teams = []
    for team_name, _kind, members in CREWS:
        team = frappe.db.get_value("PM Team", {"team_name": team_name}, "name")
        if not team:
            team = frappe.get_doc({"doctype": "PM Team", "team_name": team_name, "team_type": "Tổ đội", "is_active": 1,
                                   "leader": people["lead"] if not teams else None}).insert(ignore_permissions=True).name
        workers = []
        for full_name, trade, rate in members:
            worker = frappe.db.get_value("PMC Worker", {"full_name": full_name, "team": team}, "name")
            if not worker:
                worker = frappe.get_doc({"doctype": "PMC Worker", "full_name": full_name, "team": team, "trade": trade,
                                         "daily_rate": rate, "note": MARK}).insert(ignore_permissions=True).name
            workers.append(worker)
        teams.append((team, workers))
    days = [add_days(today, offset) for offset in range(-12, -1) if getdate(add_days(today, offset)).weekday() != 6]
    for number, day in enumerate(days):
        offset = (getdate(day) - getdate(today)).days
        active = [i for i, (first, last) in enumerate(windows[:len(works)]) if first <= offset <= last]
        if not active:
            continue
        masonry = [i for i in active if i not in (2, 6)]  # the rebar goes to the steel crew
        steel = [i for i in active if i in (2, 6)]
        for (team, workers), targets in ((teams[0], masonry), (teams[1], steel)):
            if not targets:
                continue
            lines = [{"worker": w, "task": works[targets[k % len(targets)]].name, "man_days": 1 if k % 4 else 0.5 if number % 3 == 0 else 1}
                     for k, w in enumerate(workers)]
            frappe.set_user(people["lead"])
            sheet = labour.record(project, team, day, lines)
            if number < len(days) - 1:
                frappe.set_user(people["commander"])
                labour.confirm(sheet["name"])
    frappe.set_user("Administrator")


def drop_site(projects) -> None:
    """Every stock entry, request, plan, shift, transfer, attendance sheet, store and location of these projects."""
    for project in projects:
        for name in frappe.get_all("Stock Entry", filters={"project": project}, pluck="name"):
            frappe.db.delete("Stock Entry Detail", {"parent": name})
            frappe.db.delete("Stock Ledger Entry", {"voucher_no": name})
            frappe.db.delete("GL Entry", {"voucher_no": name})
            frappe.db.delete("Stock Entry", {"name": name})
        for name in frappe.get_all("Material Request", filters={"pm_project": project}, pluck="name"):
            frappe.db.delete("Material Request Item", {"parent": name})
            frappe.db.delete("Material Request", {"name": name})
        for doctype in ("PMC Material Plan", "PMC Machine Shift", "PMC Machine Transfer"):
            frappe.db.delete(doctype, {"project": project})
        for name in frappe.get_all("PMC Crew Attendance", filters={"project": project}, pluck="name"):
            frappe.db.delete("PMC Attendance Line", {"parent": str(name)})
            frappe.db.delete("PMC Crew Attendance", {"name": name})
        for store in frappe.get_all("Warehouse", filters={"pm_project": project}, pluck="name"):
            frappe.db.delete("Bin", {"warehouse": store})
            frappe.db.delete("Warehouse", {"name": store})
        frappe.db.delete("Location", {"pm_project": project})


def remove(project: str | None) -> None:
    """The site data of the demo project and the demo's own masters."""
    if project:
        for name in frappe.get_all("Asset Movement", filters={"pm_project": project}, pluck="name"):
            frappe.db.delete("Asset Movement Item", {"parent": name})
            frappe.db.delete("Asset Movement", {"name": name})
        drop_site([project])
    codes = [code for code, *_rest in MACHINES]
    frappe.db.delete("PMC Machine Transfer", {"machine": ["in", codes]})
    for name in frappe.get_all("Asset Movement Item", filters={"asset": ["in", frappe.get_all(
            "Asset", filters={"item_code": ASSET_ITEM}, pluck="name") or [""]]}, pluck="parent"):
        frappe.db.delete("Asset Movement Item", {"parent": name})
        frappe.db.delete("Asset Movement", {"name": name})
    for doctype, filters in (("PMC Machine", {"name": ["in", codes], "note": MARK}),
                             ("PMC Worker", {"note": MARK}), ("Asset", {"item_code": ASSET_ITEM})):
        frappe.db.delete(doctype, filters)
    for team_name, *_rest in CREWS:
        frappe.db.delete("PM Team", {"team_name": team_name})
    for code, *_rest in NORMS:
        if frappe.db.get_value("PMC Material Norm", code, "note") == MARK:
            frappe.db.delete("PMC Norm Material", {"parent": code})
            frappe.db.delete("PMC Material Norm", {"name": code})
    for code in [c for c, *_rest in ITEMS] + [ASSET_ITEM]:
        if frappe.db.get_value("Item", code, "description") == MARK and not frappe.db.exists("Stock Ledger Entry",
                                                                                              {"item_code": code}):
            frappe.db.delete("Bin", {"item_code": code})
            frappe.db.delete("Item", {"name": code})
    email = KEEPER[0]
    frappe.db.delete("Notification Log", {"for_user": email})
    frappe.db.delete("PM Project Member", {"user": email})
    frappe.delete_doc("User", email, force=True, ignore_permissions=True, ignore_missing=True)
