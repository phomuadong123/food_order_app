import frappe
import os
import requests
import traceback
from frappe.utils import now

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
                "doctype": "Lunch Transaction",
                "zalo_user": user,
                "type": "Pay",
                "amount": -price,  # Trừ tiền nên số âm
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
		

