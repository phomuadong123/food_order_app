import frappe
import qrcode
import io
import base64
from frappe.utils import now, now_datetime
import requests


@frappe.whitelist()
def create_payment_request(amount,zalo_id):
    """Tạo yêu cầu thanh toán"""
    if not amount or float(amount) <= 0:
        frappe.throw("Số tiền không hợp lệ")

    user_data = frappe.db.get_value(
        "Zalo User Map", 
        {"zalo_id": zalo_id}, 
        ["name", "full_name"], # Danh sách các cột cần lấy
        as_dict=True           # Trả về dạng {key: value} để dễ truy cập
    )

    if not user_data:
        return {"success": False, "message": "Người dùng không tồn tại"}

    # Truy cập giá trị
    name = user_data.name
    full_name = user_data.full_name

    bank_info = {
        "bank": "MBBank",
        "account_number": "6636332003",  
        "account_name": "DO ANH TUAN",
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

@frappe.whitelist(allow_guest=True)
def get_payment_requests(zalo_id=None, limit=20, offset=0):
    """
    Lấy danh sách yêu cầu thanh toán bằng SQL thuần.
    Chỉ dành cho Admin.
    """
    try:
        if not zalo_id:
            return {"success": False, "message": "Zalo ID là bắt buộc"}
        
        # 1. Ép kiểu dữ liệu để tránh lỗi SQL Injection hoặc sai định dạng
        limit = frappe.utils.cint(limit)
        offset = frappe.utils.cint(offset)

        # 2. Kiểm tra quyền Admin (Dùng lại hàm helper của bạn)
        user_data = get_zalo_user_data(zalo_id)

        if not user_data:
            frappe.throw("Người dùng chưa đăng ký.", frappe.PermissionError)
      
        # 3. Truy vấn danh sách bằng SQL thuần
        # Lưu ý: Dùng %s để tránh SQL Injection
        query = """
            SELECT 
                name, user, amount, status, qr_code, 
                bank_info, transaction_id, notes, creation
            FROM 
                `tabPayment Request`
            WHERE 
                status = 'Pending'
            ORDER BY 
                creation DESC
            LIMIT %s OFFSET %s
        """
        requests = frappe.db.sql(query, (limit, offset), as_dict=True)

        # 4. Đếm tổng số bản ghi Pending để phân trang
        total_count = frappe.db.sql("""
            SELECT COUNT(*) FROM `tabPayment Request` WHERE status = 'Pending'
        """)[0][0]

        return {
            "success": True,
            "data": requests,
            "total_count": total_count,
            "user_info": user_data
        }

    except frappe.PermissionError as e:
        return {"success": False, "message": str(e)}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_payment_requests_sql_error")
        return {"success": False, "message": "Lỗi hệ thống khi lấy dữ liệu."}


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
        admin_config = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "roles")
        
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
                    "description": f"Nạp tiền được duyệt bởi {current_user} - Payment Request: {payment_request_id}",
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
        ["roles", "full_name"], 
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


