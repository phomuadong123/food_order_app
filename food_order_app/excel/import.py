import frappe
import os
import requests
import traceback
from frappe.utils import now, now_datetime, add_days, getdate
from datetime import datetime, timedelta
import calendar
import openpyxl
from frappe.utils.file_manager import get_file_path


@frappe.whitelist(allow_guest=False)
def import_yearly_report(file_url=None):
    """
    Import file Excel xuất theo năm, với nhiều sheet tương ứng với các tháng.
    Tạo Lunch Order và Transaction cho từng tháng.
    """
    if not file_url:
        frappe.throw("Cần cung cấp file_url của file Excel")

    frappe.flags.skip_update_wallet = True
    try:
        file_path = get_file_path(file_url)
        
        # 2. Mở file trực tiếp từ ổ cứng (Nhanh và không lỗi URL)
        wb = openpyxl.load_workbook(file_path, data_only=True)

        # Xử lý từng sheet (mỗi sheet là một tháng)
        for sheet_name in wb.sheetnames:
            if not sheet_name.startswith("Tháng "):
                continue

            month_part = sheet_name.replace("Tháng ", "").split("-")[0]
    
            month = int(month_part)
            ws = wb[sheet_name]

            # Tìm session cho tháng này (giả sử năm hiện tại)
            year = datetime.now().year
            session_name = frappe.db.get_value("Lunch Session", {"date": ["between", [datetime(year, month, 1), datetime(year, month, calendar.monthrange(year, month)[1])]]}, "name")
            if not session_name:
                frappe.msgprint(f"Không tìm thấy session cho tháng {month}")
                continue

            session_doc = frappe.get_doc("Lunch Session", session_name)
            menu_items = session_doc.get("menu_items")  # Giả sử có field menu_items
            if not menu_items:
                frappe.msgprint(f"Session {session_name} không có menu_items")
                continue

            # Giả sử dùng menu_item đầu tiên
            menu_item = menu_items[0].menu_item if menu_items else None
            if not menu_item:
                continue

            # Đọc dữ liệu từ sheet
            rows = list(ws.iter_rows(values_only=True))
            headers = rows[2]      # Dòng thứ 3 (index 2)
            data_rows = rows[3:]

            date_columns = []
            for i, header in enumerate(headers):
                if header and str(header).isdigit():
                    date_columns.append((i, int(header)))

            for row in data_rows:
                if not row[1]:  # Họ và tên
                    continue

                user_name = row[1]
                # Tìm Zalo User Map
                zalo_user = frappe.db.get_value("Zalo User Map", {"real_name": user_name}, "name")
                if not zalo_user:
                    continue

                # Tạo order cho những ngày có 1
                for col_idx, day in date_columns:
                    if row[col_idx] == 1:
                        order_date = datetime(year, month, day)
                        # Kiểm tra đã có order chưa
                        existing = frappe.db.exists("Lunch Order", {
                            "zalo_user": zalo_user,
                            "session": session_name,
                            "created_at": ["between", [order_date, order_date + timedelta(days=1) - timedelta(seconds=1)]]
                        })
                        if existing:
                            continue

                        # Tạo Lunch Order
                        order = frappe.get_doc({
                            "doctype": "Lunch Order",
                            "zalo_user": zalo_user,
                            "session": session_name,
                            "menu_item": menu_item,
                            "created_at": order_date,
                            "is_active": 1
                        })
                        order.insert(ignore_permissions=True)

                        # Tạo Transaction (pay)
                        transaction = frappe.get_doc({
                            "doctype": "Transaction",
                            "zalo_user": zalo_user,
                            "type": "pay",
                            "amount": -abs(frappe.db.get_value("Lunch Menu Item", menu_item, "price") or 0),
                            "reference": order.name,
                            "date": order_date,
                            "description": f"Thanh toán cho bữa ăn ngày {order_date.strftime('%d/%m/%Y')}"
                        })
                        transaction.insert(ignore_permissions=True)

        frappe.msgprint("Import thành công")

    except Exception as e:
        frappe.log_error(f"Import error: {str(e)}")
        frappe.throw(f"Lỗi import: {str(e)}")

    finally:
        frappe.flags.skip_update_wallet = False
