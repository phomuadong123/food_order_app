import frappe

def my_task():
    """Scheduled task that runs every minute and calls the notification API"""
    try:
        # Call the notification API
        frappe.call("food_order_app.api.my_notification_api")
        frappe.logger().info("Scheduled task executed successfully")
    except Exception as e:
        frappe.logger().error(f"Error in scheduled task: {str(e)}")