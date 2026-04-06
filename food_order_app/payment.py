import frappe
import api
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

