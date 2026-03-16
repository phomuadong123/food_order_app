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
            "icon": "octicon octicon-package",
            "roles": [
                {"role": "Lunch Management"},
            ],
            "sections": [
                {
                    "label": "Lunch Management",
                    "items": [
                        {
                            "type": "doctype",
                            "link_to": "Lunch Session",
                            "label": "Lunch Sessions",
                            "icon": "octicon octicon-calendar",
                        },
                        {
                            "type": "doctype",
                            "link_to": "Lunch Order",
                            "label": "Orders",
                            "icon": "octicon octicon-list-unordered",
                        },
                        {
                            "type": "doctype",
                            "link_to": "Lunch Menu Item",
                            "label": "Menu Items",
                            "icon": "octicon octicon-package",
                        },
                        {
                            "type": "doctype",
                            "link_to": "Lunch Session Menu",
                            "label": "Session Menus",
                            "icon": "octicon octicon-duplicate",
                        },
                        {
                            "type": "doctype",
                            "link_to": "Lunch Wallet",
                            "label": "Wallets",
                            "icon": "octicon octicon-credit-card",
                        },
                        {
                            "type": "doctype",
                            "link_to": "Transaction",
                            "label": "Transactions",
                            "icon": "octicon octicon-sync",
                        },
                    ],
                }
            ],
        }
    )

    workspace.insert(ignore_permissions=True)
