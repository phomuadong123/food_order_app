"""
Permission module for Food Order App
"""
import frappe


def has_app_permission(user=None):
	"""
	Check if user has permission to access Food Order App
	Returns True if user has permission, False otherwise
	"""
	if not user:
		user = frappe.session.user
	
	# Allow all logged-in users except Guest
	if user == "Guest":
		return False
	
	# You can add more granular permission checks here
	# For example: check if user has specific role
	# user_doc = frappe.get_doc("User", user)
	# return "Lunch Management" in [role.role for role in user_doc.roles]
	
	return True
