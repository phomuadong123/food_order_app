from datetime import datetime, time

import frappe
from frappe.utils import flt, getdate, now


logger = frappe.logger("lunch_admin")

# Intentionally kept separate from the legacy vote flow.
# The production vote flow is frozen to minimize regression risk.


def _require_lunch_order_management_permission():
    """Allow only users who can edit Lunch Order to use admin-only APIs."""
    if not frappe.has_permission("Lunch Order", "write"):
        frappe.throw("Bạn không có quyền quản lý đăng ký bữa ăn.", frappe.PermissionError)


def _get_locked_wallet(zalo_user):
    """Lock exactly one wallet before an administrative financial operation."""
    wallets = frappe.db.sql(
        """
        SELECT name, balance
        FROM `tabLunch Wallet`
        WHERE zalo_user = %s
        FOR UPDATE
        """,
        (zalo_user,),
        as_dict=True,
    )

    if not wallets:
        frappe.throw("Không tìm thấy ví của người dùng.")
    if len(wallets) > 1:
        frappe.throw("Người dùng có nhiều ví. Không thể tự động thay đổi số dư.")

    return wallets[0]


def _get_admin_session_menu_price(session, menu_item):
    """Return a server-side price only for an item configured on the session."""
    rows = frappe.db.sql(
        """
        SELECT mi.price
        FROM `tabLunch Session Menu` sm
        JOIN `tabLunch Menu Item` mi
            ON sm.menu_item = mi.name
        WHERE sm.parent = %s AND sm.menu_item = %s
        LIMIT 1
        """,
        (session, menu_item),
        as_dict=True,
    )
    if not rows:
        frappe.throw("Món ăn không thuộc buổi ăn đã chọn.")

    price = flt(rows[0].price)
    if price <= 0:
        frappe.throw("Giá món ăn phải lớn hơn 0 để tạo đăng ký quản trị.")

    return price


def _create_admin_lunch_order_and_pay(session, menu_item, zalo_user, price, order_datetime):
    """Create one correction order and one linked Pay transaction.

    The existing Transaction.after_insert hook updates the wallet in the same
    database transaction. This module deliberately does not call legacy vote APIs.
    """
    order_doc = frappe.get_doc(
        {
            "doctype": "Lunch Order",
            "session": session,
            "zalo_user": zalo_user,
            "is_active": 1,
            "menu_item": menu_item,
            "created_at": order_datetime,
        }
    )
    order_doc.insert(ignore_permissions=True)

    transaction = frappe.get_doc(
        {
            "doctype": "Transaction",
            "zalo_user": zalo_user,
            "type": "Pay",
            "amount": -price,
            "reference": order_doc.name,
            "session": session,
            "description": "Trừ tiền cho suất đăng ký ăn",
            "date": order_datetime,
        }
    )
    transaction.insert(ignore_permissions=True)
    return order_doc, transaction


@frappe.whitelist()
def admin_get_sessions_by_date(order_date):
    """Return sessions that may be corrected by an administrator on one date."""
    _require_lunch_order_management_permission()
    if not order_date:
        frappe.throw("Vui lòng chọn ngày ăn.")

    return {
        "success": True,
        "data": frappe.get_all(
            "Lunch Session",
            filters={
                "date": getdate(order_date),
                "status": ["in", ["Open", "Closed"]],
            },
            fields=["name", "session_name", "date", "status", "start_date", "end_date"],
            order_by="start_date asc, creation asc",
        ),
    }


@frappe.whitelist()
def admin_get_session_menu_items(session):
    """Return the actual menu items configured on one Lunch Session."""
    _require_lunch_order_management_permission()
    if not session or not frappe.db.exists("Lunch Session", session):
        frappe.throw("Không tìm thấy buổi ăn.")

    menu_items = frappe.db.sql(
        """
        SELECT mi.name, mi.item_name, mi.price
        FROM `tabLunch Session Menu` sm
        JOIN `tabLunch Menu Item` mi ON mi.name = sm.menu_item
        WHERE sm.parent = %s
        ORDER BY mi.item_name asc, mi.name asc
        """,
        (session,),
        as_dict=True,
    )
    return {"success": True, "data": menu_items}


@frappe.whitelist()
def admin_search_lunch_users(search_text=None):
    """Search Zalo users by name or Zalo ID for the administrative dialog."""
    _require_lunch_order_management_permission()
    search_text = (search_text or "").strip()
    if not search_text:
        return {"success": True, "data": []}

    like_value = f"%{search_text}%"
    users = frappe.db.sql(
        """
        SELECT
            zum.name,
            zum.full_name,
            zum.real_name,
            zum.department,
            zum.zalo_id,
            zum.is_active,
            wallet.balance AS wallet_balance
        FROM `tabZalo User Map` zum
        LEFT JOIN `tabLunch Wallet` wallet ON wallet.zalo_user = zum.name
        WHERE zum.full_name LIKE %s
           OR zum.real_name LIKE %s
           OR zum.zalo_id LIKE %s
        ORDER BY zum.full_name asc, zum.name asc
        LIMIT 20
        """,
        (like_value, like_value, like_value),
        as_dict=True,
    )
    return {"success": True, "data": users}


@frappe.whitelist()
def admin_create_lunch_order(session, menu_item, zalo_user):
    """Create one administrative order and its linked Pay transaction atomically.

    Administrative corrections intentionally allow Open and Closed sessions without
    applying the public vote deadline.
    """
    _require_lunch_order_management_permission()
    if not session or not menu_item or not zalo_user:
        frappe.throw("Thiếu buổi ăn, món ăn hoặc người dùng.")

    savepoint = "admin_create_lunch_order"
    frappe.db.savepoint(savepoint)
    try:
        session_doc = frappe.get_doc("Lunch Session", session)
        if session_doc.status not in ("Open", "Closed"):
            frappe.throw("Buổi ăn phải ở trạng thái Mở hoặc Đã đóng để có thể điều chỉnh.")
        if not session_doc.date:
            frappe.throw("Buổi ăn không có ngày ăn để ghi nhận thời gian đăng ký.")

        admin_order_datetime = datetime.combine(getdate(session_doc.date), time(0, 0, 1))

        user = frappe.db.get_value(
            "Zalo User Map",
            zalo_user,
            ["name", "full_name", "is_active"],
            as_dict=True,
        )
        if not user:
            frappe.throw("Không tìm thấy người dùng Zalo.")
        if not int(user.is_active or 0):
            frappe.throw("Người dùng chưa được kích hoạt.")

        price = _get_admin_session_menu_price(session, menu_item)
        _get_locked_wallet(zalo_user)
        order_doc, transaction = _create_admin_lunch_order_and_pay(
            session=session,
            menu_item=menu_item,
            zalo_user=zalo_user,
            price=price,
            order_datetime=admin_order_datetime,
        )
        wallet_balance = frappe.db.get_value("Lunch Wallet", {"zalo_user": zalo_user}, "balance")

        logger.info(
            "ADMIN_CREATE_LUNCH_ORDER admin=%s zalo_user=%s lunch_order=%s session=%s menu_item=%s amount=%s transaction=%s",
            frappe.session.user,
            zalo_user,
            order_doc.name,
            session,
            menu_item,
            price,
            transaction.name,
        )
        return {
            "success": True,
            "message": f"Đã thêm đăng ký cho {user.full_name}.",
            "lunch_order": order_doc.name,
            "transaction": transaction.name,
            "amount": float(price),
            "wallet_balance": float(wallet_balance or 0),
            "full_name": user.full_name,
        }
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        logger.error("ADMIN_CREATE_LUNCH_ORDER failed\n%s", frappe.get_traceback())
        raise


@frappe.whitelist()
def admin_get_active_orders_by_date(order_date):
    """Return active orders with original payment data for safe cancellation."""
    _require_lunch_order_management_permission()
    if not order_date:
        frappe.throw("Vui lòng chọn ngày ăn.")

    orders = frappe.db.sql(
        """
        SELECT
            lo.name AS lunch_order,
            lo.created_at,
            lo.session,
            lo.menu_item,
            zum.name AS zalo_user,
            zum.full_name,
            zum.real_name,
            zum.department,
            zum.zalo_id,
            ls.session_name,
            ls.date AS session_date,
            mi.item_name AS menu_item_name,
            COALESCE(
                (
                    SELECT wallet.balance
                    FROM `tabLunch Wallet` wallet
                    WHERE wallet.zalo_user = lo.zalo_user
                    ORDER BY wallet.creation asc, wallet.name asc
                    LIMIT 1
                ),
                0
            ) AS wallet_balance,
            COALESCE(
                (
                    SELECT COUNT(*)
                    FROM `tabTransaction` pay
                    WHERE pay.reference = lo.name
                      AND pay.type = 'Pay'
                      AND pay.zalo_user = lo.zalo_user
                ),
                0
            ) AS payment_transaction_count,
            COALESCE(
                (
                    SELECT SUM(-pay.amount)
                    FROM `tabTransaction` pay
                    WHERE pay.reference = lo.name
                      AND pay.type = 'Pay'
                      AND pay.zalo_user = lo.zalo_user
                ),
                0
            ) AS paid_amount
        FROM `tabLunch Order` lo
        JOIN `tabLunch Session` ls ON ls.name = lo.session
        JOIN `tabZalo User Map` zum ON zum.name = lo.zalo_user
        JOIN `tabLunch Menu Item` mi ON mi.name = lo.menu_item
        WHERE ls.date = %s AND lo.is_active = 1
        ORDER BY ls.start_date asc, lo.created_at asc, lo.name asc
        """,
        (getdate(order_date),),
        as_dict=True,
    )
    for order in orders:
        order.payment_is_resolvable = (
            int(order.payment_transaction_count or 0) == 1 and float(order.paid_amount or 0) > 0
        )

    return {"success": True, "data": orders}


@frappe.whitelist()
def admin_cancel_lunch_order(lunch_order):
    """Deactivate one order and refund its exact original Pay transaction once."""
    _require_lunch_order_management_permission()
    if not lunch_order:
        frappe.throw("Thiếu mã Lunch Order.")

    savepoint = "admin_cancel_lunch_order"
    frappe.db.savepoint(savepoint)
    try:
        locked_orders = frappe.db.sql(
            """
            SELECT name, session, zalo_user, menu_item, is_active
            FROM `tabLunch Order`
            WHERE name = %s
            FOR UPDATE
            """,
            (lunch_order,),
            as_dict=True,
        )
        if not locked_orders:
            frappe.throw("Không tìm thấy Lunch Order.")

        order = locked_orders[0]
        if not int(order.is_active or 0):
            frappe.throw("Đăng ký này đã được hủy trước đó.")

        _get_locked_wallet(order.zalo_user)

        refund_transactions = frappe.db.sql(
            """
            SELECT name
            FROM `tabTransaction`
            WHERE reference = %s AND type = 'Refund'
            FOR UPDATE
            """,
            (order.name,),
            as_dict=True,
        )
        if refund_transactions:
            frappe.throw("Đăng ký này đã có giao dịch hoàn tiền. Không thể hoàn thêm.")

        pay_transactions = frappe.db.sql(
            """
            SELECT name, amount
            FROM `tabTransaction`
            WHERE reference = %s AND type = 'Pay' AND zalo_user = %s
            ORDER BY creation asc, name asc
            FOR UPDATE
            """,
            (order.name, order.zalo_user),
            as_dict=True,
        )
        if not pay_transactions:
            frappe.throw(
                "Không tìm thấy giao dịch thanh toán của đăng ký này. "
                "Không thực hiện hoàn tiền để tránh sai lệch dữ liệu."
            )
        if len(pay_transactions) != 1:
            frappe.throw(
                "Có nhiều giao dịch thanh toán liên kết với đăng ký này. "
                "Không thể tự động hoàn tiền an toàn."
            )

        pay_transaction = pay_transactions[0]
        pay_amount = flt(pay_transaction.amount)
        if pay_amount >= 0:
            frappe.throw("Giao dịch thanh toán có số tiền không hợp lệ. Không thể hoàn tiền tự động.")
        refund_amount = abs(pay_amount)

        frappe.db.set_value("Lunch Order", order.name, "is_active", 0)
        refund_transaction = frappe.get_doc(
            {
                "doctype": "Transaction",
                "zalo_user": order.zalo_user,
                "type": "Refund",
                "amount": refund_amount,
                "reference": order.name,
                "session": order.session,
                "description": f"Hoàn tiền cho suất đăng ký ăn {order.name}",
                "date": now(),
            }
        )
        refund_transaction.insert(ignore_permissions=True)
        wallet_balance = frappe.db.get_value("Lunch Wallet", {"zalo_user": order.zalo_user}, "balance")
        user_full_name = frappe.db.get_value("Zalo User Map", order.zalo_user, "full_name")

        logger.info(
            "ADMIN_CANCEL_LUNCH_ORDER admin=%s zalo_user=%s lunch_order=%s session=%s menu_item=%s amount=%s pay_transaction=%s refund_transaction=%s",
            frappe.session.user,
            order.zalo_user,
            order.name,
            order.session,
            order.menu_item,
            refund_amount,
            pay_transaction.name,
            refund_transaction.name,
        )
        return {
            "success": True,
            "message": f"Đã hủy đăng ký của {user_full_name}.",
            "lunch_order": order.name,
            "transaction": refund_transaction.name,
            "refund_amount": refund_amount,
            "wallet_balance": float(wallet_balance or 0),
            "full_name": user_full_name,
        }
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        logger.error("ADMIN_CANCEL_LUNCH_ORDER failed\n%s", frappe.get_traceback())
        raise
