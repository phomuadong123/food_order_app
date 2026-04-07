import frappe
import qrcode
import io
import base64
from frappe.utils import now, now_datetime
from food_order_app import api


@frappe.whitelist()
def create_payment_request(amount):
    """Tạo yêu cầu thanh toán"""
    if not amount or float(amount) <= 0:
        frappe.throw("Số tiền không hợp lệ")

    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Vui lòng đăng nhập")

    # Thông tin tài khoản ngân hàng của chị Tuyết
    bank_info = {
        "bank": "MBBank",
        "account_number": "6636332003",  # Thay bằng số tài khoản thực
        "account_name": "Nguyen Thi Tuyet",
        "content": f"Nap tien {user} {now()}"
    }

    # Tạo QR code cho chuyển khoản
    qr_data = f"BANK:{bank_info['bank']};ACC:{bank_info['account_number']};AMOUNT:{amount};CONTENT:{bank_info['content']}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    # Tạo Payment Request
    pr = frappe.get_doc({
        "doctype": "Payment Request",
        "user": user,
        "amount": amount,
        "status": "Pending",
        "bank_info": f"Ngân hàng: {bank_info['bank']}\nSố tài khoản: {bank_info['account_number']}\nTên: {bank_info['account_name']}\nNội dung: {bank_info['content']}",
        "qr_code": f"data:image/png;base64,{qr_base64}"
    })
    pr.insert()

    # Gửi thông báo Zalo đến admin
    send_approval_notification(pr.name)

    return {
        "success": True,
        "payment_request": pr.name,
        "qr_code": pr.qr_code,
        "bank_info": pr.bank_info
    }

@frappe.whitelist()
def approve_payment(payment_request_name, action):
    """Duyệt hoặc từ chối thanh toán"""
    if action not in ["approve", "reject"]:
        frappe.throw("Hành động không hợp lệ")

    pr = frappe.get_doc("Payment Request", payment_request_name)
    if pr.status != "Pending":
        frappe.throw("Yêu cầu đã được xử lý")

    pr.status = "Approved" if action == "approve" else "Rejected"
    pr.approved_by = frappe.session.user
    pr.approved_at = now_datetime()
    pr.save()

    # Nếu duyệt, cập nhật ví lunch
    if action == "approve":
        zalo_user_map = frappe.db.get_value("Zalo User Map", {"user": pr.user}, "name")
        if zalo_user_map:
            wallet = frappe.get_doc("Lunch Wallet", {"zalo_user": zalo_user_map})
            wallet.balance += pr.amount
            wallet.save()

    # Gửi thông báo Zalo đến user
    send_user_notification(pr, action)

    return {"success": True}

def send_approval_notification(payment_request_name):
    """Gửi thông báo đến admin để duyệt"""
    admins = frappe.get_all("Zalo Config", filters={"can_approve_payments": 1}, fields=["zalo_user_id"])

    for admin in admins:
        if admin.zalo_user_id:
            message = f"Yêu cầu thanh toán mới: {payment_request_name}\nDuyệt: /api/method/food_order_app.payment.approve_payment?payment_request={payment_request_name}&action=approve\nTừ chối: /api/method/food_order_app.payment.approve_payment?payment_request={payment_request_name}&action=reject"
            api.send_zalo_vote_link_group(admin.zalo_user_id, message)

def send_user_notification(pr, action):
    """Gửi thông báo đến user"""
    user_zalo_id = frappe.db.get_value("Zalo User Map", {"user": pr.user}, "zalo_user_id")
    if user_zalo_id:
        if action == "approve":
            message = f"Yêu cầu thanh toán {pr.name} đã được duyệt. Số tiền {pr.amount} VNĐ đã được thêm vào ví."
        else:
            message = f"Yêu cầu thanh toán {pr.name} đã bị từ chối."
        api.send_zalo_vote_link_group(message)



# =========================
# PAYMENT ADMIN REDIRECT
# =========================

@frappe.whitelist()
def payment_admin_redirect(zalo_id=None):
    """
    Redirect admin user to payment admin page.
    Only users with can_approve_payments=1 in Zalo Config can access.
    """
    try:
        if not zalo_id:
            frappe.throw("Zalo ID is required")
        
        # Check if user exists in Zalo User Map
        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            frappe.throw("User not found")
        
        # Check if user is admin (can_approve_payments)
        admin_config = frappe.db.get_value(
            "Zalo Config",
            {"zalo_user_id": zalo_id},
            ["name", "can_approve_payments"],
            as_dict=True
        )
        
        if not admin_config or not admin_config.get("can_approve_payments"):
            frappe.throw("You do not have permission to access this page", frappe.PermissionError)
        
        # Redirect to payment admin page
        base_url = BASE_URL or frappe.utils.get_url()
        payment_admin_url = f"{base_url}/payment?mode=admin&zalo_id={zalo_id}"
        
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = payment_admin_url
        
        return {"success": True, "message": "Redirecting to payment admin page"}
        
    except frappe.PermissionError as e:
        frappe.log_error(
            message=f"[payment_admin_redirect] Access denied for zalo_id: {zalo_id}",
            title="Payment Admin Permission Error"
        )
        return {"success": False, "message": "You do not have permission to access this page"}
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="payment_admin_redirect Error"
        )
        return {"success": False, "message": str(e)}


# =========================
# GET TRANSACTIONS (for payment page)
# =========================

@frappe.whitelist()
def get_user_transactions(zalo_id, from_date=None, to_date=None, limit=10, offset=0):
    """
    Get transaction history for a user
    """
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID is required"}
        
        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            return {"success": False, "message": "User not found"}
        
        filters = {"zalo_user": user}
        
        if from_date:
            filters["date"] = [">=", from_date]
        if to_date:
            filters["date"] = ["<=", to_date]
        
        # Get transactions
        transactions = frappe.get_all(
            "Transaction",
            filters=filters,
            fields=[
                "name",
                "type",
                "amount",
                "description",
                "date"
            ],
            order_by="date desc",
            limit=limit,
            offset=offset
        )
        
        # Get total count
        total_count = frappe.db.count("Transaction", filters)
        
        return {
            "success": True,
            "data": transactions,
            "total_count": total_count
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_user_transactions Error")
        return {"success": False, "message": "Error fetching transactions"}


# =========================
# GET PAYMENT REQUESTS (for admin approval)
# =========================

@frappe.whitelist()
def get_pending_payment_requests(zalo_id=None, limit=20, offset=0):
    """
    Get pending payment requests for admin approval.
    Only admins can access this.
    """
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID is required"}
        
        # Verify user is admin
        admin_config = frappe.db.get_value(
            "Zalo Config",
            {"zalo_user_id": zalo_id},
            "can_approve_payments"
        )
        
        if not admin_config:
            frappe.throw("You do not have permission to access this", frappe.PermissionError)
        
        # Get pending payment requests
        requests = frappe.get_all(
            "Payment Request",
            filters={"status": "Pending"},
            fields=[
                "name",
                "user",
                "amount",
                "status",
                "qr_code",
                "bank_info",
                "transaction_id",
                "notes",
                "creation"
            ],
            order_by="creation desc",
            limit=limit,
            offset=offset
        )
        
        # Get total count of pending requests
        total_count = frappe.db.count("Payment Request", {"status": "Pending"})
        
        return {
            "success": True,
            "data": requests,
            "total_count": total_count
        }
    except frappe.PermissionError:
        frappe.log_error(
            message=f"[get_pending_payment_requests] Access denied for zalo_id: {zalo_id}",
            title="Payment Request Permission Error"
        )
        return {"success": False, "message": "You do not have permission to access this"}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_pending_payment_requests Error")
        return {"success": False, "message": "Error fetching payment requests"}


# =========================
# APPROVE/REJECT PAYMENT REQUEST (for admin)
# =========================

@frappe.whitelist()
def approve_payment_request(payment_request_id, zalo_id, action, notes=""):
    """
    Approve or reject a payment request (admin only)
    action: 'Approved' or 'Rejected'
    """
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID is required"}
        
        if not payment_request_id or action not in ["Approved", "Rejected"]:
            return {"success": False, "message": "Invalid parameters"}
        
        # Verify user is admin
        admin_config = frappe.db.get_value(
            "Zalo Config",
            {"zalo_user_id": zalo_id},
            "can_approve_payments"
        )
        
        if not admin_config:
            frappe.throw("You do not have permission to approve payments", frappe.PermissionError)
        
        # Get current user info
        current_user = frappe.session.user
        
        # Update payment request
        payment_req = frappe.get_doc("Payment Request", payment_request_id)
        payment_req.status = action
        payment_req.approved_by = current_user
        payment_req.approved_at = now_datetime()
        payment_req.notes = notes
        
        payment_req.save(ignore_permissions=True)
        frappe.db.commit()
        
        # If approved, add deposit transaction
        if action == "Approved":
            user_name = payment_req.user
            amount = payment_req.amount
            
            # Update wallet balance
            wallet = frappe.db.get_value("Lunch Wallet", {"zalo_user": user_name}, "name")
            if wallet:
                transaction = frappe.get_doc({
                    "doctype": "Transaction",
                    "zalo_user": user_name,
                    "type": "Deposit",
                    "amount": amount,
                    "description": f"Nạp tiền được duyệt - Payment Request: {payment_request_id}",
                    "date": now_datetime()
                })
                transaction.insert(ignore_permissions=True)
                frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Payment request {action.lower()} successfully"
        }
    except frappe.PermissionError:
        frappe.log_error(
            message=f"[approve_payment_request] Access denied for zalo_id: {zalo_id}",
            title="Approve Payment Permission Error"
        )
        return {"success": False, "message": "You do not have permission to approve payments"}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "approve_payment_request Error")
        return {"success": False, "message": "Error processing payment request"}


