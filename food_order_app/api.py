import frappe
import os
import requests
import traceback
from frappe.utils import now, today, now_datetime, add_days

logger = frappe.logger("lunch_api")

# =========================
# ZALO CONFIG
# =========================

ZALO_APP_ID = os.getenv("ZALO_APP_ID")
ZALO_SECRET = os.getenv("ZALO_SECRET")
REDIRECT_URI = os.getenv("ZALO_REDIRECT_URI")
BASE_URL = os.getenv("BASE_URL")


# =========================
# START VOTE
# =========================

@frappe.whitelist(allow_guest=True)
def start_vote(session):

    try:

        base = BASE_URL or frappe.utils.get_url()

        oauth_url = (
            f"https://oauth.zaloapp.com/v4/permission?"
            f"app_id={ZALO_APP_ID}"
            f"&redirect_uri={base}{REDIRECT_URI}"
            f"&state={session}"
        )

        frappe.log_error(oauth_url, "ZALO OAUTH URL")

        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = oauth_url

    except Exception:

        frappe.log_error(frappe.get_traceback(), "START VOTE ERROR")
        return {"error": "start_vote_failed"}


# =========================
# ZALO CALLBACK
# =========================

@frappe.whitelist(allow_guest=True)
def zalo_callback(code=None, state=None):

    frappe.log_error(f"START code={code} state={state}", "ZALO CALLBACK START")

    try:

        if not code:
            frappe.log_error("Missing OAuth code", "ZALO CALLBACK ERROR")
            return {"error": "missing_code"}

        # =====================================================
        # STEP 1: GET ACCESS TOKEN
        # =====================================================

        try:

            token_res = requests.post(
                "https://oauth.zaloapp.com/v4/access_token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "secret_key": ZALO_SECRET
                },
                data={
                    "app_id": ZALO_APP_ID,
                    "code": code,
                    "grant_type": "authorization_code"
                },
                timeout=15
            )

            frappe.log_error(
                f"STATUS={token_res.status_code} BODY={token_res.text}",
                "ZALO TOKEN RAW RESPONSE"
            )

            token_json = token_res.json()

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "ZALO TOKEN API FAILED"
            )
            return {"error": "token_api_failed"}

        access_token = token_json.get("access_token")

        if not access_token:
            frappe.log_error(str(token_json), "TOKEN NOT FOUND")
            return {"error": "token_failed", "detail": token_json}

        frappe.log_error(access_token, "ACCESS TOKEN RECEIVED")

        # =====================================================
        # STEP 2: GET USER PROFILE
        # =====================================================

        try:

            profile_res = requests.get(
                "https://graph.zalo.me/v2.0/me",
                params={
                    "fields": "id,name,picture",
                    "access_token": access_token
                },
                timeout=15
            )

            frappe.log_error(
                f"STATUS={profile_res.status_code} BODY={profile_res.text}",
                "ZALO PROFILE RAW"
            )

            profile = profile_res.json()

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "PROFILE API FAILED"
            )
            return {"error": "profile_api_failed"}

        zalo_id = profile.get("id")
        name = profile.get("name")

        picture = profile.get("picture", {})

        if isinstance(picture, dict):
            avatar = picture.get("data", {}).get("url", "")
        else:
            avatar = picture

        frappe.log_error(str(profile), "PROFILE PARSED")

        if not zalo_id:
            frappe.log_error(str(profile), "PROFILE MISSING ID")
            return {"error": "profile_failed"}

        # =====================================================
        # STEP 3: FIND USER
        # =====================================================

        try:

            user = frappe.db.exists(
                "Zalo User Map",
                {"zalo_id": zalo_id}
            )

            frappe.log_error(str(user), "USER EXISTS RESULT")
            frappe.log_error(frappe.local.site, "CURRENT SITE")

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "USER LOOKUP FAILED"
            )
            return {"error": "user_lookup_failed"}

        # =====================================================
        # STEP 4: CREATE USER
        # =====================================================

        if not user:

            try:

                user_doc = frappe.get_doc({
                    "doctype": "Zalo User Map",
                    "zalo_id": zalo_id,
                    "full_name": name,
                    "avatar": avatar,
                    "created_at": now()
                })

                user_doc.insert(ignore_permissions=True)

                frappe.db.commit()

                frappe.log_error(
                    user_doc.as_json(),
                    "USER INSERTED DATA"
                )

                user = user_doc.name

            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "USER INSERT FAILED"
                )
                return {"error": "user_create_failed"}

            # =====================================================
            # STEP 5: CREATE WALLET
            # =====================================================

            try:

                wallet_doc = frappe.get_doc({
                    "doctype": "Lunch Wallet",
                    "zalo_user": user,
                    "balance": 0,
                    "updated_at": now()
                })

                wallet_doc.insert(ignore_permissions=True)

                frappe.db.commit()

                frappe.log_error(
                    wallet_doc.name,
                    "WALLET CREATED"
                )

            except Exception:

                frappe.log_error(
                    frappe.get_traceback(),
                    "WALLET CREATE FAILED"
                )

        # =====================================================
        # STEP 6: REDIRECT
        # =====================================================

        vote_page = f"/vote?session={state}&zalo_id={zalo_id}"

        frappe.log_error(vote_page, "REDIRECT TO VOTE PAGE")

        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = vote_page

        return

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "ZALO CALLBACK FATAL ERROR"
        )

        return {
            "error": "callback_crash",
            "trace": frappe.get_traceback()
        }


# =========================
# UPDATE SESSION STATS
# =========================

def update_session_stats(session):

    try:

        result = frappe.db.sql(
            """
            SELECT COUNT(*), SUM(price)
            FROM `tabLunch Order`
            WHERE session=%s
            """,
            session
        )[0]

        total_orders = result[0] or 0
        total_amount = result[1] or 0

        frappe.db.set_value(
            "Lunch Session",
            session,
            {
                "total_orders": total_orders,
                "total_amount": total_amount
            }
        )

        frappe.log_error(
            f"{session} orders={total_orders} amount={total_amount}",
            "SESSION STATS UPDATED"
        )

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "SESSION STATS ERROR"
        )


# =========================
# CREATE VOTE LINK
# =========================

def create_vote_link(doc, method):

    try:

        base = frappe.utils.get_url()

        link = f"{base}/api/method/food_order_app.api.start_vote?session={doc.name}"

        frappe.db.set_value(
            "Lunch Session",
            doc.name,
            "vote_link",
            link
        )

        frappe.log_error(
            link,
            "VOTE LINK CREATED"
        )

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "CREATE VOTE LINK ERROR"
        )

def update_session_menu_items(doc, method=None):
    try:
        frappe.db.delete("Lunch Session Menu", {"parent": doc.name})

        if hasattr(doc, 'menu_items') and doc.menu_items:
            for row in doc.menu_items:
                if row.menu_item:
                    new_link = frappe.get_doc({
                        "doctype": "Lunch Session Menu",
                        "parent": doc.name,
                        "parenttype": "Lunch Session",
                        "parentfield": "menu_items",
                        "menu_item": row.menu_item
                    })
                    new_link.insert(ignore_permissions=True)
        
        frappe.db.commit()

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Lỗi cập nhật danh sách Menu"
        )
		
@frappe.whitelist(allow_guest=True)
def get_menu(session):

    try:

        logger.info(f"get_menu called session={session}")

        if not session:
            frappe.throw("Session is required")

        items = frappe.db.sql("""
            SELECT
                mi.name,
                mi.item_name,
                mi.price
            FROM `tabLunch Session Menu` sm
            JOIN `tabLunch Menu Item` mi
                ON sm.menu_item = mi.name
            WHERE sm.parent = %s
        """, (session,), as_dict=True)

        logger.info(f"menu count={len(items)}")

        return {
            "success": True,
            "data": items
        }

    except Exception:

        error = traceback.format_exc()

        logger.error(error)

        frappe.log_error(
            title="get_menu error",
            message=error
        )

        return {
            "success": False,
            "message": "Failed to get menu"
        }

@frappe.whitelist(allow_guest=True)
def vote(session, menu_item, zalo_id):

    try:
        logger.info(f"[VOTE] session={session}, menu_item={menu_item}, zalo_id={zalo_id}")

        # ====================================
        # 1. VALIDATE INPUT
        # ====================================
        if not session or not menu_item or not zalo_id:
            return {"success": False, "message": "Missing parameters"}

        # ====================================
        # 2. GET SESSION
        # ====================================
        try:
            session_doc = frappe.get_doc("Lunch Session", session)
        except Exception:
            logger.error(f"[VOTE] Session not found: {session}")
            return {"success": False, "message": "Session not found"}

        if session_doc.status != "Open":
            return {"success": False, "message": "Session is not open"}

        # ====================================
        # 3. GET USER
        # ====================================
        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            return {"success": False, "message": "User not found"}

        # ====================================
        # 4. CHECK DUPLICATE ORDER
        # ====================================
        existed = frappe.db.exists("Lunch Order", {"session": session, "zalo_user": user})
        if existed:
            return {"success": False, "message": "User already ordered"}

        # ====================================
        # 5. GET PRICE (JOIN Lunch Session Menu + Lunch Menu Item)
        # ====================================
        row = frappe.db.sql("""
            SELECT mi.price
            FROM `tabLunch Session Menu` sm
            JOIN `tabLunch Menu Item` mi
                ON sm.menu_item = mi.name
            WHERE sm.parent = %s AND sm.menu_item = %s
            LIMIT 1
        """, (session, menu_item), as_dict=True)

        if not row:
            return {"success": False, "message": "Menu item not available today"}

        price = row[0].price
        logger.info(f"[VOTE] PRICE={price}")

        # ====================================
        # 6. GET WALLET
        # ====================================
        wallet_name = frappe.db.get_value("Lunch Wallet", {"zalo_user": user}, "name")
        wallet_balance = frappe.db.get_value("Lunch Wallet", wallet_name, "balance")

        if wallet_balance is None:
            return {"success": False, "message": "Wallet not found"}

        logger.info(f"[VOTE] WALLET balance={wallet_balance}")

        # ====================================
        # 7. INSERT ORDER
        # ====================================
        try:
            order_doc = frappe.get_doc({
                "doctype": "Lunch Order",
                "session": session,
                "zalo_user": user,
                "menu_item": menu_item,
                "created_at": now()
            })

            order_doc.insert(ignore_permissions=True)

            transaction = frappe.get_doc({
                "doctype": "Transaction",
                "zalo_user": user,
                "type": "Pay",
                "amount": -price,  # Trừ tiền nên số âm
                "reference": order_doc.name, # Ghi nhận order vừa tạo
                "date": now()
            })

            transaction.insert(ignore_permissions=True)

            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            logger.error(traceback.format_exc())
            return {"success": False, "message": "Failed to create order"}

        logger.info(f"[VOTE] ORDER CREATED name={order_doc.name}")

        # ====================================
        # 9. SUCCESS
        # ====================================
        return {"success": True, "message": "Order success", "order": order_doc.name}

    except Exception:
        frappe.db.rollback()
        error = traceback.format_exc()
        logger.error(f"[VOTE] ERROR {error}")
        return {"success": False, "message": "Internal error"}

@frappe.whitelist()
def update_wallet_on_transaction(doc, method=None):
    wallet = frappe.get_doc("Lunch Wallet", {"zalo_user": doc.zalo_user})
    
    if not wallet:
        frappe.throw(f"Không tìm thấy ví cho người dùng {doc.zalo_user}")
    
    new_balance = wallet.balance + doc.amount

    wallet.balance = new_balance
    wallet.updated_at = frappe.utils.now_datetime()
    wallet.save(ignore_permissions=True)

    frappe.msgprint(f"Ví của {doc.zalo_user} đã được cập nhật. Số dư: {new_balance:,.0f}đ")	

# =========================
# AUTO SESSION DAILY RENEWAL
# =========================
def send_zalo_vote_link(zalo_id, vote_link, menu_date):
    """
    Sử dụng Zalo OA API để gửi tin nhắn thông báo link chọn món
    Yêu cầu thiết lập config ZALO_OA_TOKEN trong site config
    """
    token = frappe.conf.get("zalo_oa_token")
    if not token:
        logger.warning("ZALO_OA_TOKEN is missing. Could not send the daily vote link.")
        return
        
    url = "https://openapi.zalo.me/v3.0/oa/message/cs"
    
    payload = {
        "recipient": {
            "user_id": zalo_id
        },
        "message": {
            "text": f"🔔 Đã có thực đơn ăn trưa ngày {menu_date}!\nKính mời anh/chị chọn món qua liên kết sau:\n{vote_link}"
        }
    }
    
    headers = {
        "access_token": token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        logger.info(f"[Zalo Message] Sent vote link to {zalo_id} - Response: {response.text}")
    except Exception as e:
        logger.error(f"[Zalo Message] Failed to send message to {zalo_id}: {str(e)}")


def check_and_renew_sessions():

    logger.info("=== START check_and_renew_sessions ===")

    try:

        expired_sessions = frappe.db.sql("""
            SELECT name
            FROM `tabLunch Session`
            WHERE status='Open'
            AND end_date < NOW()
        """, as_dict=True)

        logger.info(f"Expired sessions found: {len(expired_sessions)}")

        if not expired_sessions:
            return

        for s in expired_sessions:

            session_name = s["name"]

            logger.info(f"Processing session: {session_name}")

            # đóng session cũ
            frappe.db.sql("""
                UPDATE `tabLunch Session`
                SET status='Closed'
                WHERE name=%s
            """, session_name)

            today_date = today()
            start_time = now_datetime()
            tomorrow = add_days(today_date, 1)
            end_time = f"{tomorrow} 10:30:00"

            new_name = frappe.generate_hash(length=10)

            # tạo session mới
            frappe.db.sql("""
                INSERT INTO `tabLunch Session`
                (name, session_name, date, start_date, end_date, status, creation, modified)
                VALUES (%s,%s,%s,%s,%s,'Open',NOW(),NOW())
            """, (
                new_name,
                f"Menu {today_date}",
                today_date,
                start_time,
                end_time
            ))

            logger.info(f"Created new session: {new_name}")

            # copy menu items
            menu_items = frappe.db.sql("""
                SELECT menu_item
                FROM `tabLunch Session Menu`
                WHERE parent=%s
            """, session_name, as_dict=True)

            logger.info(f"Copying {len(menu_items)} menu items")

            for item in menu_items:

                frappe.db.sql("""
                    INSERT INTO `tabLunch Session Menu`
                    (name,parent,parenttype,parentfield,menu_item,creation,modified)
                    VALUES (%s,%s,'Lunch Session','menu_items',%s,NOW(),NOW())
                """, (
                    frappe.generate_hash(10),
                    new_name,
                    item["menu_item"]
                ))

        frappe.db.commit()

        logger.info("Database commit success")

    except Exception:

        error_trace = traceback.format_exc()

        logger.error(error_trace)

        frappe.log_error(
            title="Scheduler check_and_renew_sessions failed",
            message=error_trace
        )

        frappe.db.rollback()


@frappe.whitelist(allow_guest=False)
def export_monthly_report(month=None, year=None):
    """
    Export Excel Report cho Lunch Session
    Method: GET /api/method/food_order_app.api.export_monthly_report?month=3&year=2026
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    import calendar
    from datetime import datetime
    
    if not month or not year:
        now = datetime.now()
        month = now.month
        year = now.year
        
    month = int(month)
    year = int(year)
    
    # 1. Tính số ngày trong tháng
    _, days_in_month = calendar.monthrange(year, month)
    
    # 2. Lấy dữ liệu Order
    orders = frappe.db.sql("""
        SELECT 
            lo.zalo_user,
            DAY(ls.date) as order_day,
            lmi.price
        FROM `tabLunch Order` lo
        JOIN `tabLunch Session` ls ON lo.session = ls.name
        JOIN `tabLunch Menu Item` lmi ON lo.menu_item = lmi.name
        WHERE MONTH(ls.date) = %s AND YEAR(ls.date) = %s AND ls.status != 'Draft'
    """, (month, year), as_dict=True)
    
    user_orders = {}
    for o in orders:
        zalo_user = o.zalo_user
        if zalo_user not in user_orders:
            user_orders[zalo_user] = {'days': set(), 'total_amount': 0}
        user_orders[zalo_user]['days'].add(o.order_day)
        user_orders[zalo_user]['total_amount'] += (o.price or 0)
        
    # 3. Lấy dữ liệu Ví
    wallets = frappe.get_all("Lunch Wallet", fields=["zalo_user", "balance"])
    wallet_map = {w.zalo_user: w.balance for w in wallets}
    
    # 4. Tạo file Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Tháng {month}-{year}"
    
    header_fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
    header_font = Font(bold=True)
    center_align = Alignment(horizontal='center', vertical='center')
    
    # Dòng 1 (Merge ô hiển thị "Ngày")
    ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=2+days_in_month)
    day_cell = ws.cell(row=1, column=3, value="Ngày")
    day_cell.alignment = center_align
    day_cell.font = header_font
    day_cell.fill = header_fill
    
    # Style phần còn lại của dòng 1
    for col in range(1, 3+days_in_month+4):
        c = ws.cell(row=1, column=col)
        c.fill = header_fill
    
    # Dòng 2 (Tiêu đề cụ thể)
    headers = ["STT", "Họ và tên"] + list(range(1, days_in_month + 1)) + [
        "Số ngày ăn", "Đơn giá suất ăn \n(VNĐ)", "Thành tiền \n(VNĐ)", "Số tiền còn lại \n(VNĐ)"
    ]
    ws.append(headers)
    
    # Style dòng 2
    for col_idx, value in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.fill = header_fill
        
        # Căn chỉnh độ rộng cột
        if col_idx == 1:
            ws.column_dimensions[get_column_letter(col_idx)].width = 5
        elif col_idx == 2:
            ws.column_dimensions[get_column_letter(col_idx)].width = 25
        elif col_idx > 2 and col_idx <= 2 + days_in_month:
            ws.column_dimensions[get_column_letter(col_idx)].width = 4
        else:
            ws.column_dimensions[get_column_letter(col_idx)].width = 15
            
    # 5. Đổ dữ liệu
    users = frappe.get_all("Zalo User Map", fields=["name", "full_name"])
    stt = 1
    
    for u in users:
        u_data = user_orders.get(u.name, {'days': set(), 'total_amount': 0})
        num_days = len(u_data['days'])
        total_price = u_data['total_amount']
        avg_price = (total_price / num_days) if num_days > 0 else 0
        balance = wallet_map.get(u.name, 0)
        
        row_data = [stt, u.full_name]
        
        # Cột ngày (1-31)
        for d in range(1, days_in_month + 1):
            row_data.append(1 if d in u_data['days'] else "")
            
        # Các cột tổng hợp
        row_data.extend([
            num_days,
            avg_price,
            total_price,
            balance
        ])
        
        ws.append(row_data)
        
        # Style row data
        curr_row = ws.max_row
        for col_idx in range(1, len(row_data) + 1):
            cell = ws.cell(row=curr_row, column=col_idx)
            if col_idx > 2: # Can_center số
                cell.alignment = center_align
            # Format tiền tệ
            if col_idx in [len(row_data) - 2, len(row_data) - 1, len(row_data)]:
                cell.number_format = '#,##0'
                
        stt += 1
        
    # Cố định header
    ws.freeze_panes = "C3"

    # Trả về File    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    frappe.response['filename'] = f"BaoCao_AnTrua_Thang_{month}_{year}.xlsx"
    frappe.response['filecontent'] = output.getvalue()
    frappe.response['type'] = 'binary'
