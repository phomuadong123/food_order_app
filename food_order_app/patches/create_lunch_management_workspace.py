import frappe


def execute():
    """Create a dedicated "Lunch Management" Role and Workspace.

    This patch is intended to be idempotent: it will not create duplicate
    records if they already exist.
    """

    create_lunch_management_role()
    create_lunch_management_workspace()


def create_lunch_management_role():
    role_name = "Lunch Management"
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role_name,
        }).insert(ignore_permissions=True)


def create_lunch_management_workspace():
    workspace_name = "Lunch Management"

    if frappe.db.exists("Workspace", workspace_name):
        return

    workspace = frappe.get_doc(
        {
            "doctype": "Workspace",
            "name": workspace_name,
            "title": workspace_name,
            "module": "Food Order App",
            "icon": "fa fa-cutlery",
            "roles": [
                {"role": "Lunch Management"},
            ],
            "sections": [
                {
                    "label": "Lunch Management",
                    "items": [
                        {"type": "doctype", "link_to": "Lunch Session", "label": "Lunch Sessions"},
                        {"type": "doctype", "link_to": "Lunch Order", "label": "Orders"},
                        {"type": "doctype", "link_to": "Lunch Menu Item", "label": "Menu Items"},
                        {"type": "doctype", "link_to": "Lunch Session Menu", "label": "Session Menus"},
                        {"type": "doctype", "link_to": "Lunch Wallet", "label": "Wallets"},
                        {"type": "doctype", "link_to": "Transaction", "label": "Transactions"},
                    ],
                }
            ],
        }
    )

    workspace.insert(ignore_permissions=True)
