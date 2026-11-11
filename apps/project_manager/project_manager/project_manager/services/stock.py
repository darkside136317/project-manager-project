"""Stock of the core (M8): the project of a material request is the project of each of its rows.

Industry layers build their flows (site stores, issues by work item...) on ERPNext's stock documents; the core only
keeps the project consistent and narrows who sees what (permissions.stock_query, has_stock_permission).
"""


def copy_project(doc, method=None):
    """Material Request validate: rows without a project take the request's (ERPNext reports and costs read the rows)."""
    if doc.get("pm_project"):
        for row in doc.get("items") or []:
            row.project = row.project or doc.pm_project
