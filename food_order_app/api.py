import frappe
import os
import requests
import traceback
from frappe.utils import now, now_datetime, add_days, getdate
from datetime import datetime, timedelta

logger = frappe.logger("lunch_api")

# =========================
# ZALO CONFIG
# =========================

ZALO_APP_ID = os.getenv("ZALO_APP_ID")
ZALO_SECRET = os.getenv("ZALO_SECRET")
REDIRECT_URI = os.getenv("ZALO_REDIRECT_URI")
ZALO_OA_ACCESS_TOKEN = os.getenv("ZALO_OA_ACCESS_TOKEN")
GROUP_ID_ZALO = os.getenv("GROUP_ID_ZALO")
BASE_URL = os.getenv("BASE_URL")


# =========================
# START VOTE
# =========================

@frappe.whitelist(allow_guest=True)
def start_vote(session = None):
    if not ZALO_APP_ID:
        frappe.log_error("ZALO_APP_ID is not configured", "start_vote")
        return {"error": "start_vote_failed", "detail": "ZALO_APP_ID not configured"}

    if not REDIRECT_URI:
        frappe.log_error("REDIRECT_URI is not configured", "start_vote")
        return {"error": "start_vote_failed", "detail": "REDIRECT_URI not configured"}

    if not session:
        session = frappe.db.get_value("Lunch Session", filters={}, fieldname="name", order_by="creation desc")
        if not session:
            frappe.log_error("No Lunch Session found in database", "start_vote")
            return {"error": "start_vote_failed", "detail": "No active session available"}

    try:
        base = BASE_URL or frappe.utils.get_url()
        redirect_uri = f"{base}{REDIRECT_URI}"

        from urllib.parse import quote_plus
        encoded_redirect_uri = quote_plus(redirect_uri)

        oauth_url = (
            f"https://oauth.zaloapp.com/v4/permission?"
            f"app_id={ZALO_APP_ID}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&state={session}"
        )

        frappe.log_error(
            title="start_vote_debug",
            message=f"FORCING NGROK CALLBACK: {oauth_url}"
        )

        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = oauth_url
        return

    except Exception as err:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"start_vote failed: {str(err)}"
        )
        return {"error": "start_vote_failed", "detail": str(err)}


# =========================
# ZALO CALLBACK
# =========================

@frappe.whitelist(allow_guest=True)
def zalo_callback(code=None, state=None):

    trace_id = frappe.generate_hash(length=8)

    def log(msg):
        frappe.log_error(
            message=f"[{trace_id}] {msg}",
            title="zalo_callback"
        )

    try:

        if not code:
            log("ERROR | Missing OAuth code")
            return {"error": "missing_code"}
        
        # STEP 1: GET ACCESS TOKEN
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
            token_json = token_res.json()
            log(f"STEP 1 RAW RESPONSE | {token_json}")

        except Exception as e:
            log(f"STEP 1 FAILED | {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"[{trace_id}] TOKEN TRACE")
            return {"error": "token_api_failed"}

        access_token = token_json.get("access_token")

        if not access_token:
            log("STEP 1 ERROR | access_token missing")
            return {"error": "token_failed"}

        # STEP 2: GET PROFILE
        config = frappe.db.sql("""
            SELECT name, app_id, secret_key, refresh_token, proxy_url
            FROM `tabZalo Config` 
            LIMIT 1
        """, as_dict=True)
        
        config = config[0]
        proxy_url = config.get("proxy_url")
        proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }

        try:

            profile_res = requests.get(
                "https://graph.zalo.me/v2.0/me",
                params={
                    "fields": "id,name,picture",
                    "access_token": access_token
                },
                proxies=proxies,
                timeout=15
            )
            profile = profile_res.json()

        except Exception as e:
            log(f"STEP 2 FAILED | {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"[{trace_id}] PROFILE TRACE")
            return {"error": "profile_api_failed"}

        zalo_id = profile.get("id")
        name = profile.get("name")

        picture = profile.get("picture", {})
        avatar = picture.get("data", {}).get("url", "") if isinstance(picture, dict) else picture

        if not zalo_id:
            log("STEP 2 ERROR | missing zalo_id")
            return {"error": "profile_failed"}

        # STEP 3: FIND USER
        try:
            user = frappe.db.exists("Zalo User Map", {"zalo_id": zalo_id})

        except Exception as e:
            log(f"STEP 3 FAILED | {str(e)}")
            frappe.log_error(frappe.get_traceback(), f"[{trace_id}] USER LOOKUP TRACE")
            return {"error": "user_lookup_failed"}

        # STEP 4: CREATE USER
        if not user:
            try:

                user_doc = frappe.get_doc({
                    "doctype": "Zalo User Map",
                    "zalo_id": zalo_id,
                    "full_name": name,
                    "avatar": avatar,
                    "is_active": 0,
                    "created_at": now()
                })

                user_doc.insert(ignore_permissions=True)
                frappe.db.commit()

                user = user_doc.name


            except Exception as e:
                log(f"STEP 4 FAILED | {str(e)}")
                frappe.log_error(frappe.get_traceback(), f"[{trace_id}] USER CREATE TRACE")
                return {"error": "user_create_failed"}

            # STEP 5: WALLET
            try:

                wallet_doc = frappe.get_doc({
                    "doctype": "Lunch Wallet",
                    "zalo_user": user,
                    "balance": 0,
                    "updated_at": now()
                })

                wallet_doc.insert(ignore_permissions=True)
                frappe.db.commit()

            except Exception as e:
                log(f"STEP 5 FAILED | {str(e)}")
                frappe.log_error(frappe.get_traceback(), f"[{trace_id}] WALLET TRACE")

        # STEP 6: REDIRECT

        PRODUCTION_DOMAIN = BASE_URL
        final_url = f"{PRODUCTION_DOMAIN}/vote?session={state or ''}&zalo_id={zalo_id}"

        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = final_url

        return

    except Exception as e:
        log(f"FATAL ERROR | {str(e)}")
        frappe.log_error(frappe.get_traceback(), f"[{trace_id}] FATAL TRACE")

        return {"error": "callback_crash"}


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

        logger.info(f"{session} orders={total_orders} amount={total_amount}")

    except Exception as e:

        err_trace = frappe.get_traceback()
        logger.error(f"SESSION STATS ERROR: {e}")
        logger.debug(err_trace)


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

        logger.info(f"VOTE LINK CREATED: {link}")

    except Exception as e:

        err_trace = frappe.get_traceback()
        logger.error(f"CREATE VOTE LINK ERROR: {e}")
        logger.debug(err_trace)


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

    except Exception as e:
        err_trace = frappe.get_traceback()
        logger.error(f"Lỗi cập nhật danh sách Menu: {e}")
        logger.debug(err_trace)

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
def vote(session, menu_item, zalo_id, quantity=1):
    try:
        if not session or not menu_item or not zalo_id:
            return {"success": False, "message": "Thiếu thông tin cần thiết"}

        # 2. GET SESSION
        try:
            session_doc = frappe.get_doc("Lunch Session", session)
        except Exception:
            logger.error(f"[VOTE] Session not found: {session}")
            return {"success": False, "message": "Không tìm thấy phiên đăng ký bữa ăn"}

        if session_doc.status != "Open":
            return {"success": False, "message": "Phiên bữa ăn đã đóng, không thể đăng ký"}
        if session_doc.end_date:
            current_time = now_datetime()
            if current_time > session_doc.end_date:
                return {
                    "success": False, 
                    "message": f"Đã quá hạn đăng ký (Hạn cuối: {frappe.utils.format_datetime(session_doc.end_date, 'HH:mm dd/MM/yyyy')})"
                }
        # 3. GET USER
        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            return {"success": False, "message": "Người dùng không tồn tại"}

        is_active = frappe.db.get_value("Zalo User Map", user, "is_active")
        if not int(is_active or 0):
            return {"success": False, "message": "Vui lòng đợi admin kích hoạt tài khoản"}

        # 5. GET PRICE (JOIN Lunch Session Menu + Lunch Menu Item)
        row = frappe.db.sql("""
            SELECT mi.price
            FROM `tabLunch Session Menu` sm
            JOIN `tabLunch Menu Item` mi
                ON sm.menu_item = mi.name
            WHERE sm.parent = %s AND sm.menu_item = %s
            LIMIT 1
        """, (session, menu_item), as_dict=True)

        if not row:
            return {"success": False, "message": "Danh sách đăng ký bữa ăn không có sẵn hôm nay"}

        price = row[0].price

        # 6. GET WALLET
        wallet_name = frappe.db.get_value("Lunch Wallet", {"zalo_user": user}, "name")
        wallet_balance = frappe.db.get_value("Lunch Wallet", wallet_name, "balance")

        if wallet_balance is None:
            return {"success": False, "message": "không tìm thấy ví của người dùng"}

        logger.info(f"[VOTE] WALLET balance={wallet_balance}")

        # 7. INSERT ORDER
        try:
            quantity = int(quantity or 1)
            for i in range(quantity):
                order_doc = frappe.get_doc({
                    "doctype": "Lunch Order",
                    "session": session,
                    "zalo_user": user,
                    "is_active": 1,
                    "menu_item": menu_item,
                    "created_at": now()
                })
                order_doc.insert(ignore_permissions=True)

                transaction = frappe.get_doc({
                    "doctype": "Transaction",
                    "zalo_user": user,
                    "type": "Pay",
                    "amount": -price, 
                    "reference": order_doc.name,
                    "session": session,
                    "description": f"Trừ tiền cho suất đăng ký ăn{f' thứ {i+1} (Tổng số suất ăn: {quantity})' if quantity > 1 else ''}",
                    "date": now()
                })
                transaction.insert(ignore_permissions=True)

            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "Error Trace")
            return {"success": False, "message": "Tạo order đăng ký bữa ăn thất bại"}

        # 9. SUCCESS
        return {"success": True, "message": "Đăng ký bữa ăn thành công", "order": order_doc.name}

    except Exception:
        frappe.db.rollback()
        error = traceback.format_exc()
        logger.error(f"[VOTE] ERROR {error}")
        return {"success": False, "message": "Lỗi khi đăng ký bữa ăn"}

@frappe.whitelist(allow_guest=True)
def cancel_vote(session, zalo_id):
    try:
        if not session or not zalo_id:
            return {"success": False, "message": "Thiếu tham số đầu vào"}

        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            return {"success": False, "message": "Người dùng không tồn tại"}

        active_orders = frappe.get_all("Lunch Order", 
            filters={
                "session": session, 
                "zalo_user": user, 
                "is_active": 1
            }, 
            fields=["name", "menu_item"]
        )

        if not active_orders:
            return {"success": False, "message": "Không tìm thấy đăng ký bữa ăn nào để hủy"}

        total_refund_amount = 0
        cancelled_order_names = []

        for order in active_orders:
            price = frappe.db.get_value("Lunch Menu Item", order.menu_item, "price") or 0
            
            frappe.db.set_value("Lunch Order", order.name, "is_active", 0)
            
            total_refund_amount += price
            cancelled_order_names.append(order.name)

        if total_refund_amount > 0:
            refund_tx = frappe.get_doc({
                "doctype": "Transaction",
                "zalo_user": user,
                "type": "Refund",
                "amount": total_refund_amount,
                "session": session,
                "description": f"Hoàn tiền cho {len(cancelled_order_names)} đơn hàng đã hủy",
                "date": frappe.utils.now()
            })
            refund_tx.insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            "success": True, 
            "message": f"Đã hủy thành công {len(cancelled_order_names)} đăng ký. Tổng tiền hoàn: {total_refund_amount}"
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Cancel Vote Error")
        return {"success": False, "message": f"Có lỗi xảy ra: {str(e)}"}

@frappe.whitelist(allow_guest=True)
def get_order_status(session, zalo_id):
    try:
        if not session or not zalo_id:
            return {"success": False, "message": "Missing parameters"}

        user_info = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, ["name", "full_name"], as_dict=True)
        
        if not user_info:
            return {"success": False, "message": "Người dùng không tồn tại"}

        # Lấy thông tin phiên ăn
        session_data = frappe.db.get_value("Lunch Session", session, ["date", "start_date", "end_date"], as_dict=True)
        
        if not session_data:
            return {"success": False, "message": "Phiên đăng ký bữa ăn không tồn tại"}

        has_order = frappe.db.exists("Lunch Order", {
            "session": session, 
            "zalo_user": user_info.name,
            "is_active": 1
        })

        return {
            "success": True,
            "has_order": bool(has_order),
            "date": str(session_data.date),
            "start_date": str(session_data.start_date),
            "end_date": str(session_data.end_date),
            "full_name": user_info.full_name
        }

    except Exception:
        error = traceback.format_exc()
        # Đảm bảo bạn đã import logger hoặc dùng frappe.log_error
        frappe.log_error(title="GET_ORDER_STATUS Error", message=error)
        return {"success": False, "message": "An error occurred. Please check logs."}

@frappe.whitelist(allow_guest=True)
def get_user_activation_status(zalo_id):
    try:
        if not zalo_id:
            return {"success": False, "message": "Missing zalo_id"}

        row = frappe.db.get_value(
            "Zalo User Map",
            {"zalo_id": zalo_id},
            ["name", "is_active"],
            as_dict=True
        )
        if not row:
            return {"success": False, "message": "User not found"}

        is_active = bool(int(row.is_active or 0))
        return {
            "success": True,
            "is_active": is_active,
            "message": "OK" if is_active else "đợi admin active"
        }
    except Exception:
        error = traceback.format_exc()
        logger.error(f"[GET_USER_ACTIVATION_STATUS] ERROR {error}")
        return {"success": False, "message": "Internal error"}

@frappe.whitelist(allow_guest=True)
def get_support_group_info():
    try:
        row = frappe.get_all(
            "Zalo Group",
            fields=["group_id", "group_link", "modified"],
            order_by="modified desc",
            limit=1
        )

        if not row:
            return {"success": True, "data": None}

        return {"success": True, "data": row[0]}
    except Exception:
        error = traceback.format_exc()
        logger.error(f"[GET_SUPPORT_GROUP_INFO] ERROR {error}")
        return {"success": False, "message": "Internal error"}

@frappe.whitelist(allow_guest=True)
def get_session_votes(session):
    try:
        if not session:
            return {"success": False, "message": "Missing session"}

        # Get session date to determine the month
        session_doc = frappe.get_doc("Lunch Session", session)
        session_date = getdate(session_doc.date)
        start_of_month = datetime.combine(session_date.replace(day=1), datetime.min.time())
        end_of_month = datetime.combine((session_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1), datetime.max.time())
        end_of_previous_month = datetime.combine(start_of_month - timedelta(days=1), datetime.max.time())

        rows = frappe.db.sql("""
            SELECT
                lo.name AS order_id,
                zum.real_name AS voter_name,
                zum.full_name AS zalo_name,
                lmi.item_name AS menu_item_name,
                lmi.price,
                lo.created_at,
                CASE
                    WHEN ROW_NUMBER() OVER (
                        PARTITION BY lo.zalo_user
                        ORDER BY lo.created_at ASC, lo.creation ASC
                    ) > 1 THEN 'Đăng ký thêm'
                    ELSE ''
                END AS note,
                COALESCE(wallet.balance, 0) AS wallet_balance,
                COALESCE(prev_balance.beginning_balance, 0) AS beginning_balance,
                COALESCE(order_summary.monthly_order_count, 0) AS monthly_order_count,
                COALESCE(order_summary.monthly_food_cost, 0) AS monthly_food_cost,
                COALESCE(deposit_summary.monthly_deposit_amount, 0) AS monthly_deposit_amount
            FROM `tabLunch Order` lo
            LEFT JOIN `tabZalo User Map` zum
                ON lo.zalo_user = zum.name
            LEFT JOIN `tabLunch Menu Item` lmi
                ON lo.menu_item = lmi.name
            LEFT JOIN `tabLunch Wallet` wallet
                ON wallet.zalo_user = lo.zalo_user
            LEFT JOIN (
                SELECT
                    t.zalo_user,
                    SUM(t.amount) AS beginning_balance
                FROM `tabTransaction` t
                WHERE t.date <= %s
                GROUP BY t.zalo_user
            ) prev_balance ON prev_balance.zalo_user = lo.zalo_user
            LEFT JOIN (
                SELECT
                    lo2.zalo_user,
                    COUNT(*) AS monthly_order_count,
                    SUM(IFNULL(lmi2.price, 0)) AS monthly_food_cost
                FROM `tabLunch Order` lo2
                LEFT JOIN `tabLunch Menu Item` lmi2 ON lo2.menu_item = lmi2.name
                WHERE lo2.is_active = 1
                    AND lo2.created_at >= %s
                    AND lo2.created_at <= %s
                GROUP BY lo2.zalo_user
            ) order_summary ON order_summary.zalo_user = lo.zalo_user
            LEFT JOIN (
                SELECT
                    t3.zalo_user,
                    SUM(t3.amount) AS monthly_deposit_amount
                FROM `tabTransaction` t3
                WHERE t3.type = 'Deposit'
                    AND t3.date >= %s
                    AND t3.date <= %s
                GROUP BY t3.zalo_user
            ) deposit_summary ON deposit_summary.zalo_user = lo.zalo_user
            WHERE lo.session = %s
                AND lo.is_active = 1
            ORDER BY lo.created_at DESC, lo.creation DESC
        """, (
            end_of_previous_month,
            start_of_month,
            end_of_month,
            start_of_month,
            end_of_month,
            session,
        ), as_dict=True)

        return {"success": True, "data": rows}
    except Exception:
        error = traceback.format_exc()
        logger.error(f"[GET_SESSION_VOTES] ERROR {error}")
        return {"success": False, "message": "Internal error"}


@frappe.whitelist(allow_guest=True)
def get_my_session_transactions(zalo_id, session=None, from_date=None, to_date=None, page=1, page_size=10):
    try:
        if not zalo_id:
            return {"success": False, "message": "Thiếu thông tin tham số"}

        user = frappe.db.get_value("Zalo User Map", {"zalo_id": zalo_id}, "name")
        if not user:
            return {"success": False, "message": "Người dùng không tồn tại"}

        voter_data = frappe.db.get_value(
            "Zalo User Map",
            user,
            ["full_name", "real_name", "zalo_id"],
            as_dict=True,
        )

        wallet_balance = frappe.db.get_value("Lunch Wallet", {"zalo_user": user}, "balance") or 0

        filters = ["t.zalo_user = %s"]
        args = [user]

        if session:
            filters.append("(t.session = %s OR t.type = 'Deposit')")
            args.append(session)
            filters.append("NOT (t.type = 'Refund' AND t.session = %s AND t.description LIKE N'Hoàn tiền cho %% đơn hàng đã hủy')")
            args.append(session)
        if from_date:
            filters.append("DATE(t.date) >= %s")
            args.append(from_date)
        if to_date:
            filters.append("DATE(t.date) <= %s")
            args.append(to_date)

        where_clause = " AND ".join(filters)
        
        # Xử lý phân trang
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or 10))
        offset = (page - 1) * page_size

        # 1. Lấy tổng số bản ghi
        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabTransaction` t LEFT JOIN `tabLunch Order` lo ON t.reference = lo.name AND lo.is_active = 1 WHERE {where_clause} AND (t.type != 'pay' OR lo.name IS NOT NULL)",
            tuple(args),
        )[0][0] or 0

        # 2. Truy vấn dữ liệu (Lưu ý dấu %% để fix lỗi bạn gặp)
        query = f"""
            SELECT
                t.name AS transaction_id,
                zu.full_name AS user_real_name,
                zu.real_name AS user_zalo_name,
                CASE 
                    WHEN t.type = 'pay' THEN N'Trả tiền'
                    WHEN t.type = 'deposit' THEN N'Nạp tiền'
                    WHEN t.type = 'refund' THEN N'Hoàn tiền'
                    ELSE t.type 
                END AS transaction_type_vn,
                t.amount,
                CASE 
                    WHEN t.type = 'pay' AND lo.name IS NOT NULL 
                    THEN CONCAT(
                        N'Trừ tiền cho bữa ăn ngày ',
                        DATE_FORMAT(
                            DATE_ADD(
                                lo.created_at,
                                INTERVAL (TIME(lo.created_at) > '12:00:00') DAY
                            ),
                            '%%d/%%m/%%Y'
                        )
                    )
                    ELSE t.description 
                END AS display_description,
                t.date AS registration_time,
                COALESCE(lmi.item_name, '') AS menu_item_name,
                SUM(t.amount) OVER (PARTITION BY t.zalo_user ORDER BY t.date ASC, t.name ASC) AS running_balance
            FROM `tabTransaction` t
            LEFT JOIN `tabZalo User Map` zu ON t.zalo_user = zu.name
            LEFT JOIN `tabLunch Order` lo ON t.reference = lo.name AND lo.is_active = 1
            LEFT JOIN `tabLunch Menu Item` lmi ON lo.menu_item = lmi.name
            WHERE {where_clause} AND (t.type != 'pay' OR lo.name IS NOT NULL)
            ORDER BY t.date DESC, t.name DESC
            LIMIT %s OFFSET %s
        """
        
        selection_args = args + [page_size, offset]

        all_rows = frappe.db.sql(query, tuple(selection_args), as_dict=True)

        return {
            "success": True,
            "data": all_rows,
            "voter_name": voter_data.get("full_name") if voter_data else "",
            "wallet_balance": float(wallet_balance),
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    except Exception:
        error = traceback.format_exc()
        return {"success": False, "message": error}


@frappe.whitelist()
def update_wallet_on_transaction(doc, method=None):
    # Khi import bulk, có thể set frappe.flags.skip_update_wallet = True để bỏ qua cập nhật số dư
    if getattr(frappe.flags, "skip_update_wallet", False):
        return

    wallet = frappe.get_doc("Lunch Wallet", {"zalo_user": doc.zalo_user})
    
    if not wallet:
        frappe.throw(f"Không tìm thấy ví cho người dùng {doc.zalo_user}")
    
    new_balance = wallet.balance + doc.amount

    wallet.balance = new_balance
    wallet.updated_at = frappe.utils.now_datetime()
    wallet.save(ignore_permissions=True)

    frappe.msgprint(f"Ví người dùng đã được cập nhật. Số dư: {new_balance:,.0f}đ")	

# =========================
# AUTO SESSION DAILY RENEWAL
# =========================

def refresh_zalo_tokens():
    try:
        config = frappe.db.sql("""
            SELECT name, app_id, secret_key, refresh_token 
            FROM `tabZalo Config` 
            LIMIT 1
        """, as_dict=True)

        if not config:
            frappe.log_error("Bảng tabZalo Config trống rỗng. Hãy tạo 1 bản ghi trước!", "Zalo SQL Error")
            return None
        
        config = config[0]
        doc_name = config["name"] # Tên bản ghi để dùng cho WHERE

        # 2. Gọi API Zalo
        url = "https://oauth.zaloapp.com/v4/oa/access_token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'secret_key': config["secret_key"]
        }
        payload = {
            'refresh_token': config["refresh_token"],
            'app_id': config["app_id"],
            'grant_type': 'refresh_token'
        }

        response = requests.post(url, headers=headers, data=payload)
        res_data = response.json()

        if "access_token" in res_data:
            new_at = res_data["access_token"]
            new_rt = res_data["refresh_token"]

            # 3. UPDATE theo phong cách SQL bảng thường như bạn muốn
            frappe.db.sql("""
                UPDATE `tabZalo Config`
                SET 
                    access_token = %s,
                    refresh_token = %s
                WHERE name = %s
            """, (new_at, new_rt, doc_name))
            
            frappe.db.commit()
            return new_at
        else:
            frappe.log_error(f"Zalo trả về lỗi: {res_data}", "Zalo API Fail")
            return None

    except Exception:
        error_msg = traceback.format_exc()
        frappe.log_error(title="Zalo SQL refresh Error", message=error_msg)
        return None
    
def call_zalo_api(endpoint, method="GET", data=None):
    try:
        # Lấy access_token từ bảng riêng
        at_result = frappe.db.sql("""
            SELECT access_token 
            FROM `tabZalo Config` 
            LIMIT 1
        """)
        
        if not at_result:
            return {"error": -1, "message": "No Config Found"}
            
        at = at_result[0][0]
        headers = {'access_token': at}

        # Gọi API
        if method == "GET":
            response = requests.get(endpoint, headers=headers).json()
        else:
            response = requests.post(endpoint, headers=headers, json=data).json()

        # Nếu hết hạn thì Refresh
        if response.get("error") == -216:
            new_at = refresh_zalo_tokens()
            if new_at:
                headers['access_token'] = new_at
                # Thử lại lần 2
                if method == "GET":
                    response = requests.get(endpoint, headers=headers).json()
                else:
                    response = requests.post(endpoint, headers=headers, json=data).json()
                    
        return response

    except Exception:
        frappe.log_error(traceback.format_exc(), "call_zalo_api SQL Failed")
        return {"error": -1}

def send_zalo_vote_link_group(message):
    """
    Gửi thực đơn vào nhóm Zalo bằng GMF - Đã tích hợp tự động Refresh Token
    """
    url = "https://openapi.zalo.me/v3.0/oa/group/message"

    payload = {
        "recipient": {
            "group_id": GROUP_ID_ZALO  
        },
        "message": {
            "text": message
        }
    }

    try:
        response_data = call_zalo_api(url, method="POST", data=payload)
        
        if response_data.get("error") == 0:
            logger.info(f"[Zalo Group] Gửi thành công! Response: {response_data}")
        else:
            logger.error(f"[Zalo Group] Gửi thất bại: {response_data}")
            
    except Exception as e:
        logger.error(f"[Zalo Group] Lỗi hệ thống: {str(e)}")


@frappe.whitelist(allow_guest=True)
def check_and_renew_sessions():
    try:
        
        today_date = add_days(getdate(), 1)

        existing_today = frappe.db.sql("""
            SELECT name
            FROM `tabLunch Session`
            WHERE date = %s
            LIMIT 1
        """, today_date)

        if existing_today:
            logger.info("Session for today already exists -> EXIT")
            return

        # lấy session gần nhất
        last_session = frappe.db.sql("""
            SELECT *
            FROM `tabLunch Session`
            ORDER BY creation DESC
            LIMIT 1
        """, as_dict=True)

        if not last_session:
            logger.info("No Lunch Session found")
            return

        last_session = last_session[0]

        # check hết hạn
        expired = frappe.db.sql("""
            SELECT name
            FROM `tabLunch Session`
            WHERE name=%s
            AND status='Open'
            AND end_date < %s
        """, (last_session["name"] , today_date))

        if not expired:
            logger.info("Session not expired")
            return

        logger.info(f"Session expired: {last_session['name']}")

        # đóng session cũ
        frappe.db.sql("""
            UPDATE `tabLunch Session`
            SET status='Closed'
            WHERE name=%s
        """, last_session["name"])

        # tạo session mới
        new_name = frappe.generate_hash(10)
        link = f"{BASE_URL}/api/method/food_order_app.api.start_vote?session={new_name}"
        start_time = datetime.combine(getdate(), last_session["start_date"].time())
        end_time = datetime.combine(today_date, last_session["end_date"].time())

        frappe.db.sql("""
            INSERT INTO `tabLunch Session`
            (
                name,
                session_name,
                date,
                start_date,
                end_date,
                status,
                vote_link,
                created_by,
                creation,
                modified
            )
            VALUES (%s,%s,%s,%s,%s,'Open',%s,'Administrator',%s,%s)
        """, (
            new_name,
            f"Menu {today_date}",
            today_date,
            start_time,
            end_time,
            link,
            today_date,today_date
        ))

        logger.info(f"Created new session: {new_name}")

        # 5️⃣ copy menu từ session cũ
        frappe.db.sql("""
            INSERT INTO `tabLunch Session Menu`
            (
                name,
                parent,
                parenttype,
                parentfield,
                menu_item,
                creation,
                modified
            )
            SELECT
                UUID(),
                %s,
                'Lunch Session',
                'menu_items',
                menu_item,
                %s,
                %s
            FROM `tabLunch Session Menu`
            WHERE parent=%s
        """, (new_name, today_date, today_date, last_session["name"]))

        frappe.db.commit()

        message = f"🔔 Đã có lịch đăng ký ăn trưa ngày {today_date}!\nKính mời anh/chị đăng ký tại:\n{link}"

        send_zalo_vote_link_group(message)

        logger.info("Database commit success")

    except Exception:

        error_trace = traceback.format_exc()

        logger.error(error_trace)

        frappe.log_error(
            title="check_and_renew_sessions failed",
            message=error_trace
        )

        frappe.db.rollback()

@frappe.whitelist(allow_guest=True)
def remind_vote_today():
    """
    Gửi tin nhắc lúc 7h sáng: 
    Đã có X người chọn món rồi, đừng quên bình chọn nhé!
    """
    try:
        today_date = getdate()

        session = frappe.db.sql("""
            SELECT name, vote_link
            FROM `tabLunch Session`
            WHERE date=%s AND status='Open'
            LIMIT 1
        """, today_date, as_dict=True)

        if not session:
            logger.info("No open session for today -> EXIT")
            return

        session = session[0] 
        session_name = session["name"]
        vote_link = session["vote_link"]

        vote_count = frappe.db.sql("""
            SELECT COUNT(*) 
            FROM `tabLunch Order`
            WHERE session=%s AND is_active=1
        """, session_name)[0][0]

        message = (
            f"⏰ Nhắc hẹn đăng ký bữa trưa ngày {today_date}!\n"
            f"Hiện tại đã có {vote_count} người đăng ký bữa rồi.\n"
            f"Đừng quên đăng ký tại đây nhé!\n"
            f"{vote_link}"
        )

        # gửi group zalo
        send_zalo_vote_link_group(message)

    except Exception:
        error = traceback.format_exc()
        logger.error(error)
        frappe.log_error("remind_vote_today failed", error)

@frappe.whitelist(allow_guest=True)
def remind_close_session():
    try:
        today_date = getdate()

        session = frappe.db.sql("""
            SELECT name, vote_link
            FROM `tabLunch Session`
            WHERE date=%s AND status='Open'
            LIMIT 1
        """, today_date, as_dict=True)

        if not session:
            logger.info("No open session for today -> EXIT")
            return

        session = session[0] 
        session_name = session["name"]
        vote_link = session["vote_link"]

        vote_count = frappe.db.sql("""
            SELECT COUNT(*) 
            FROM `tabLunch Order`
            WHERE session=%s AND is_active=1
        """, session_name)[0][0]

        message = (
            f"⏰ Thông báo kết thúc phiên đặt bữa trưa ngày {today_date}!\n"
            f"Hiện tại đã có {vote_count} lượt đăng ký ăn trưa.\n"
            f"Chúc anh chị có bữa trưa ngon miệng!\n"
            f"Anh chị có thể xem lịch sử đăng ký tại đây:\n"
            f"{vote_link}"
        )

        # gửi group zalo
        send_zalo_vote_link_group(message)

    except Exception:
        error = traceback.format_exc()
        logger.error(error)
        frappe.log_error("remind_vote_today failed", error)

