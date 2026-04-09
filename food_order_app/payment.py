import frappe
import qrcode
import io
import base64
from frappe.utils import now, now_datetime
import requests
from food_order_app.api import call_zalo_api


@frappe.whitelist(allow_guest=True)
def create_payment_request(amount,zalo_id):
    """Tạo yêu cầu thanh toán"""
    if not amount or float(amount) <= 0:
        frappe.throw("Số tiền không hợp lệ")

    user_data = frappe.db.get_value(
        "Zalo User Map", 
        {"zalo_id": zalo_id}, 
        ["name", "full_name"], 
        as_dict=True           
    )

    if not user_data:
        return {"success": False, "message": "Người dùng không tồn tại"}

    # Truy cập giá trị
    name = user_data.name
    full_name = user_data.full_name

    bank_info = {
        "bank": "BIDV",
        "account_number": "3453098888",  
        "account_name": "BUI THI TUYET",
        "content": f"Nap tien cho user {full_name} vào thoi gian: {now()}"
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
        "user": name,
        "full_name": full_name,
        "amount": amount,
        "status": "Pending",
        "bank_info": f"Ngân hàng: {bank_info['bank']}\nSố tài khoản: {bank_info['account_number']}\nTên: {bank_info['account_name']}\nNội dung: {bank_info['content']}",
        "qr_code": f"data:image/png;base64,{qr_base64}"
    })
    pr.insert(ignore_permissions=True)

    # Gửi thông báo Zalo đến admin
    message = (
            f"Yêu cầu nạp tiền mới từ {full_name} - Số tiền: {amount} VNĐ. Vui lòng kiểm tra và duyệt yêu cầu này."
            f"Vui lòng kiểm tra và duyệt yêu cầu tại link!\n"
            f"{frappe.utils.get_url()}/api/method/food_order_app.api.payment_request"
        )
    notify_admins_by_zalo(message)
    return {
        "success": True,
        "payment_request": pr.name,
        "qr_code": pr.qr_code,
        "bank_info": pr.bank_info
    }


def send_zalo_message(user_id, message_text):
    try:
        config = frappe.get_all(
            "Zalo Config",
            fields=["name", "app_id", "secret_key", "refresh_token", "access_token"],
            limit=1
        )
       
        if not config:
            frappe.throw("Missing Zalo Config")

        config = config[0]
        access_token = (config.get("access_token") or "").strip()
        url = "https://openapi.zalo.me/v2.0/oa/message"

        headers = {
            "access_token": access_token,
            "Content-Type": "application/json"
        }

        payload = {
            "recipient": {
                "user_id": user_id
            },
            "message": {
                "text": message_text
            }
        }

        response = requests.post(url, json=payload, headers=headers)
        result = response.json()

        # Log để debug
        frappe.log_error(
            title="Zalo Send Message",
            message=str(result)
        )

        return result

    except Exception as e:
        frappe.log_error(
            title="Zalo Send Message Error",
            message=frappe.get_traceback()
        )
        return {"error": str(e)}


@frappe.whitelist(allow_guest=True)
def notify_admins_by_zalo(message):
    """Gửi tin nhắn Zalo OA cho tất cả admin trong Zalo User Map."""
    try:
        admins = frappe.get_all(
            "Zalo User Map",
            filters={"roles": "Admin"},
            fields=["zalo_id"]
        )

        if not admins:
            return {"success": False, "message": "Không tìm thấy admin nào."}

        sent = 0
        for admin in admins:
            if admin.zalo_id:
                if send_zalo_message(admin.zalo_id, message):
                    sent += 1

        return {
            "success": True,
            "sent": sent,
            "total": len(admins)
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "notify_admins_by_zalo Error")
        return {"success": False, "message": str(e)}


# =========================
# GET PAYMENT REQUESTS (for admin approval)
# =========================

@frappe.whitelist(allow_guest=True)
def get_payment_requests(zalo_id=None, from_date=None, to_date=None, limit=20, offset=0, isAdmin=False):
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID là bắt buộc"}
        
        limit = frappe.utils.cint(limit)
        offset = frappe.utils.cint(offset)

        user_data = get_zalo_user_data(zalo_id)
        if not user_data:
            frappe.throw("Người dùng chưa đăng ký.", frappe.PermissionError)

        # Xử lý điều kiện lọc SQL
        conditions = []
        params = []
        clauses = []

        isAdmin = str(isAdmin).lower() in ["1", "true"]
        if not isAdmin:
            clauses.append("user = %s")
            params.append(user_data.name)

        if from_date:
            conditions.append("creation >= %s")
            params.append(from_date + " 00:00:00")
        if to_date:
            conditions.append("creation <= %s")
            params.append(to_date + " 23:59:59")

        clauses.extend(conditions)
        where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""

        # Truy vấn dữ liệu
        query = f"""
            SELECT name, user,full_name, amount, status, qr_code, bank_info, transaction_id, notes, creation
            FROM `tabPayment Request`
            {where_clause}
            ORDER BY creation DESC
            LIMIT %s OFFSET %s
        """

        # Thêm limit và offset vào params
        data_params = params + [limit, offset]
        requests = frappe.db.sql(query, tuple(data_params), as_dict=True)

        # Đếm tổng số để phân trang
        count_query = f"SELECT COUNT(*) FROM `tabPayment Request` {where_clause}"
        total_count = frappe.db.sql(count_query, tuple(params))[0][0]

        return {
            "success": True,
            "data": requests,
            "total_count": total_count,
            "user_info": user_data
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_payment_requests_error")
        return {"success": False, "message": str(e)}


# =========================
# APPROVE/REJECT PAYMENT REQUEST (for admin)
# =========================

@frappe.whitelist(allow_guest=True)
def approve_payment_request(payment_request_id, zalo_id, action, notes="", price=None):
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
        admin_config = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "roles")
        
        if not admin_config:
            frappe.throw("You do not have permission to approve payments", frappe.PermissionError)
        
        # Get current user info
        current_user = get_zalo_user_data(zalo_id)
        if not current_user:
            frappe.throw("You do not have permission to approve payments", frappe.PermissionError)
        
        # Update payment request
        payment_req = frappe.get_doc("Payment Request", payment_request_id)
        payment_req.status = action
        payment_req.approved_by = current_user.name
        payment_req.approved_at = now_datetime()
        payment_req.notes = notes
        if price is not None:
            payment_req.amount = float(price)

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
                    "description": f"Nạp tiền được duyệt bởi {current_user.full_name} - Payment Request: {payment_request_id}",
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
    


def get_zalo_user_data(zalo_id):
    """Hàm nội bộ để lấy dữ liệu từ DB"""
    if not zalo_id:
        return None
        
    return frappe.db.get_value(
        "Zalo User Map", 
        {"zalo_id": zalo_id}, 
        ["roles", "full_name","name"], 
        as_dict=True
    )

@frappe.whitelist(allow_guest=True)
def check_zalo_admin(zalo_id):
    user_data = get_zalo_user_data(zalo_id)

    if not user_data:
        return {
            "is_admin": False,
            "full_name": None,
            "status": "not_found",
            "message": "Không tìm thấy người dùng này hoặc zalo_id trống."
        }

    role = user_data.roles
    full_name = user_data.full_name

    is_admin = (role == "Admin")

    return {
        "is_admin": is_admin,
        "full_name": full_name,
        "status": "success",
        "message": "Người dùng là Admin." if is_admin else "Người dùng không có quyền Admin."
    }


@frappe.whitelist()
def get_user_transactions(zalo_id, from_date=None, to_date=None, limit=10, offset=0):
    """
    Get transaction history for a user
    """
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID is required"}
        
        # Get user from Zalo User Map
        user_data = get_zalo_user_data(zalo_id)
        if not user_data:
            return {"success": False, "message": "User not found"}
        
        user_name = user_data.name
        
        # Build filters
        filters = {"zalo_user": user_name}
        
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
                "date",
                "reference",
                "session"
            ],
            order_by="date desc, creation desc",
            limit=limit,
            start=offset
        )
        
        # Get wallet balance
        wallet_balance = frappe.db.get_value("Lunch Wallet", {"zalo_user": user_name}, "balance") or 0
        
        # Format transaction types
        for tx in transactions:
            if tx.type == "Pay":
                tx.transaction_type_vn = "Trả tiền"
            elif tx.type == "Deposit":
                tx.transaction_type_vn = "Nạp tiền"
            elif tx.type == "Refund":
                tx.transaction_type_vn = "Hoàn tiền"
            else:
                tx.transaction_type_vn = tx.type
            
            # Format amount with currency
            tx.amount_formatted = f"{tx.amount:,.0f} VNĐ"
            
            # Format date
            tx.date_formatted = frappe.utils.format_datetime(tx.date, "dd/MM/yyyy HH:mm")
        
        return {
            "success": True,
            "data": transactions,
            "wallet_balance": float(wallet_balance),
            "user_info": {
                "full_name": user_data.full_name
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_user_transactions: {str(e)}", "Payment API")
        return {"success": False, "message": "Error retrieving transaction history"}


