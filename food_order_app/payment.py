import frappe
import qrcode
import io
import base64
from frappe.utils import now, now_datetime
import requests


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
        "account_number": "6636332003",  
        "account_name": "DO ANH TUAN",
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

    return {
        "success": True,
        "payment_request": pr.name,
        "qr_code": pr.qr_code,
        "bank_info": pr.bank_info
    }

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
    


@frappe.whitelist(allow_guest=True)
def check_zalo_admin(zalo_id):
    if not zalo_id:
        return {
            "status": "error",
            "message": "Thiếu zalo_id"
        }

    role = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "roles")

    if not role:
        return {
            "is_admin": False,
            "status": "not_found",
            "message": "Không tìm thấy người dùng này."
        }

    if role == "Admin":
        return {
            "is_admin": True,
            "status": "success",
            "message": "Người dùng là Admin."
        }
    else:
        return {
            "is_admin": False,
            "status": "success",
            "message": "Người dùng không có quyền Admin."
        }


