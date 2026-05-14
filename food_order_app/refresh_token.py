import frappe
import requests
import traceback
import json
from datetime import datetime


def zalo_log(title, data):

    try:

        if isinstance(data, (dict, list)):
            data = json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )

        frappe.log_error(
            title=title,
            message=str(data)
        )

    except Exception:

        frappe.log_error(
            title="ZALO LOG ERROR",
            message=traceback.format_exc()
        )


# =========================================================
# REFRESH TOKEN DAILY SCHEDULER
# =========================================================
def daily_refresh_zalo_token():

    try:

        zalo_log(
            "ZALO DAILY REFRESH",
            "Start scheduled refresh token job"
        )

        config = frappe.db.sql("""
            SELECT
                name,
                app_id,
                secret_key,
                refresh_token
            FROM `tabZalo Config`
            LIMIT 1
        """, as_dict=True)

        if not config:

            zalo_log(
                "ZALO DAILY REFRESH ERROR",
                "No Zalo Config found"
            )

            return

        config = config[0]

        doc_name = config["name"]

        url = "https://oauth.zaloapp.com/v4/oa/access_token"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": config["secret_key"]
        }

        payload = {
            "refresh_token": config["refresh_token"],
            "app_id": config["app_id"],
            "grant_type": "refresh_token"
        }

        zalo_log(
            "ZALO DAILY REFRESH REQUEST",
            {
                "url": url,
                "payload": payload
            }
        )

        response = requests.post(
            url,
            headers=headers,
            data=payload,
            timeout=30
        )

        zalo_log(
            "ZALO DAILY REFRESH STATUS",
            response.status_code
        )

        zalo_log(
            "ZALO DAILY REFRESH RAW RESPONSE",
            response.text
        )

        try:

            res_data = response.json()

        except Exception:

            zalo_log(
                "ZALO DAILY REFRESH JSON ERROR",
                response.text
            )

            return

        zalo_log(
            "ZALO DAILY REFRESH RESPONSE",
            res_data
        )

        # =====================================================
        # SUCCESS
        # =====================================================
        if "access_token" in res_data:

            new_at = res_data.get("access_token")
            new_rt = res_data.get("refresh_token")

            frappe.db.sql("""
                UPDATE `tabZalo Config`
                SET
                    access_token = %s,
                    refresh_token = %s,
                    last_refresh_at = NOW()
                WHERE name = %s
            """, (
                new_at,
                new_rt,
                doc_name
            ))

            frappe.db.commit()

            zalo_log(
                "ZALO DAILY REFRESH SUCCESS",
                {
                    "message": "Refresh token success",
                    "time": str(datetime.now())
                }
            )

        # =====================================================
        # FAILED
        # =====================================================
        else:

            zalo_log(
                "ZALO DAILY REFRESH FAILED",
                res_data
            )

            # OPTIONAL:
            # đánh dấu cần login lại

            frappe.db.sql("""
                UPDATE `tabZalo Config`
                SET need_relogin = 1
                WHERE name = %s
            """, (doc_name,))

            frappe.db.commit()

    except Exception:

        zalo_log(
            "ZALO DAILY REFRESH SYSTEM ERROR",
            traceback.format_exc()
        )