import os
import json
import string
import random
import logging
from datetime import datetime, timezone
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests

from db import (
    decrement_join,
    find_participant_for_invite,
    get_leaderboard_rows,
    get_participant_by_id,
    get_participant_by_username,
    get_participant_stats,
    increment_join,
    init_db,
    insert_participant,
    list_participants,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
logging.basicConfig(level=logging.INFO)

# ==== الإعدادات (تحطها كمتغيرات بيئة في السيرفر) ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")          # توكن البوت من BotFather
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")        # مثال: -1001234567890 (آيدي القناة الرقمي)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")  # جزء سري برابط الويبهوك

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def normalize_username(raw):
    """يوحّد شكل معرف تيليجرام: بدون @ وبدون مسافات وبأحرف صغيرة (المعرفات غير حساسة لحالة الأحرف)."""
    return (raw or "").strip().lstrip("@").strip().lower()


def random_code(n=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def utcnow():
    return datetime.now(timezone.utc)


def get_leaderboard_data():
    """يرجع أفضل 5 مشتركين + إحصائيات عامة، تُستخدم بصفحة المتصدرين وواجهة الـ API."""
    top5_rows = get_leaderboard_rows()
    total_participants, total_joins = get_participant_stats()

    top5 = [{"name": row["name"], "joins_count": row["joins_count"]} for row in top5_rows]
    return {
        "top5": top5,
        "total_participants": total_participants,
        "total_joins": total_joins,
    }


# ---------------------------------------------------------------
# صفحة إنشاء الحساب: اسم + معرف تيليجرام + كلمة مرور ⟵ رابط دعوة خاص
# ---------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET" and session.get("participant_id"):
        return redirect(url_for("account"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not name or not username:
            flash("الرجاء إدخال الاسم ومعرف تيليجرام")
            return redirect(url_for("home"))
        if len(password) < 6:
            flash("كلمة المرور لازم تكون 6 أحرف على الأقل")
            return redirect(url_for("home"))
        if password != confirm:
            flash("كلمتا المرور غير متطابقتين")
            return redirect(url_for("home"))

        if get_participant_by_username(username):
            flash("هذا المعرف مسجّل مسبقاً — سجّل الدخول بدلاً من ذلك")
            return redirect(url_for("participant_login"))

        link_name = f"{username}-{random_code(5)}"[:32]

        try:
            resp = requests.post(
                f"{API_URL}/createChatInviteLink",
                json={"chat_id": CHANNEL_ID, "name": link_name},
                timeout=15,
            )
            data = resp.json()
            if not data.get("ok"):
                flash(f"خطأ من تيليجرام: {data.get('description')}")
                return redirect(url_for("home"))

            invite_link = data["result"]["invite_link"]
            password_hash = generate_password_hash(password, method="pbkdf2:sha256")
            new_id = insert_participant(
                name, username, password_hash, invite_link, link_name, utcnow()
            )

            session["participant_id"] = new_id
            return redirect(url_for("account"))

        except Exception as e:
            flash(f"حدث خطأ: {e}")
            return redirect(url_for("home"))

    return render_template("index.html")


# ---------------------------------------------------------------
# تسجيل دخول المشترك لحسابه الحالي
# ---------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def participant_login():
    if request.method == "GET" and session.get("participant_id"):
        return redirect(url_for("account"))

    if request.method == "POST":
        username = normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")

        participant = get_participant_by_username(username)

        if participant and check_password_hash(participant["password_hash"], password):
            session["participant_id"] = participant["id"]
            return redirect(url_for("account"))

        flash("المعرف أو كلمة المرور غير صحيحة")
        return redirect(url_for("participant_login"))

    return render_template("participant_login.html")


# ---------------------------------------------------------------
# صفحة حساب المشترك: رابطه الخاص + عدد انضماماته الحالي
# ---------------------------------------------------------------
@app.route("/account")
def account():
    if not session.get("participant_id"):
        flash("سجّل الدخول أولاً للوصول لحسابك")
        return redirect(url_for("participant_login"))

    participant = get_participant_by_id(session["participant_id"])

    if not participant:
        session.pop("participant_id", None)
        flash("الحساب غير موجود، سجّل الدخول من جديد")
        return redirect(url_for("participant_login"))

    return render_template("account.html", participant=participant)


@app.route("/api/my-stats")
def api_my_stats():
    if not session.get("participant_id"):
        return jsonify({"error": "not_logged_in"}), 401

    participant = get_participant_by_id(session["participant_id"])

    if not participant:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"joins_count": participant["joins_count"]})


# ---------------------------------------------------------------
# ويبهوك تيليجرام: يستقبل إشعار كل ما ينضم عضو جديد للقناة
# ---------------------------------------------------------------
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    chat_member = update.get("chat_member")

    if chat_member:
        new_status = chat_member.get("new_chat_member", {}).get("status")
        old_status = chat_member.get("old_chat_member", {}).get("status")
        invite_link_obj = chat_member.get("invite_link")

        joined = (
            new_status in ("member", "restricted")
            and old_status not in ("member", "administrator", "creator", "restricted")
        )

        if joined:
            user = chat_member.get("new_chat_member", {}).get("user", {})
            joined_name = user.get("username") or user.get("first_name") or "مستخدم"
            joined_user_id = user.get("id")
            participant = find_participant_for_invite(invite_link_obj)

            if participant and joined_user_id:
                increment_join(participant["id"], joined_user_id, joined_name, utcnow())
                app.logger.info(
                    "Counted join for participant %s via %s",
                    participant["id"],
                    (invite_link_obj or {}).get("invite_link")
                    or (invite_link_obj or {}).get("name"),
                )
            else:
                app.logger.warning(
                    "Join not matched to participant. invite_link=%s new=%s old=%s",
                    invite_link_obj,
                    new_status,
                    old_status,
                )

        left = (
            new_status in ("left", "kicked")
            and old_status in ("member", "restricted")
        )

        if left:
            user = chat_member.get("new_chat_member", {}).get("user", {})
            joined_user_id = user.get("id")
            if joined_user_id:
                participant_id = decrement_join(joined_user_id, utcnow())
                if participant_id:
                    app.logger.info(
                        "Counted leave for participant %s user %s",
                        participant_id,
                        joined_user_id,
                    )
                else:
                    app.logger.warning(
                        "Leave not matched to prior join. user=%s new=%s old=%s",
                        joined_user_id,
                        new_status,
                        old_status,
                    )

    return {"ok": True}


# ---------------------------------------------------------------
# لوحة التحكم: عرض كل المشتركين وعدد من جلبهم كل واحد
# ---------------------------------------------------------------
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if not session.get("is_admin"):
        if request.method == "POST":
            if request.form.get("password") == ADMIN_PASSWORD:
                session["is_admin"] = True
                return redirect(url_for("dashboard"))
            flash("كلمة المرور خطأ")
        return render_template("login.html")

    participants = list_participants()
    total_joins = sum(p.get("joins_count", 0) for p in participants)

    return render_template("dashboard.html", participants=participants, total_joins=total_joins)


@app.route("/logout")
def logout():
    was_admin = session.pop("is_admin", None)
    session.pop("participant_id", None)
    if was_admin:
        return redirect(url_for("dashboard"))
    return redirect(url_for("home"))


# ---------------------------------------------------------------
# لوحة المتصدرين العلنية: أفضل 5 مشتركين، بدون كلمة مرور
# ---------------------------------------------------------------
@app.route("/leaderboard")
def leaderboard():
    data = get_leaderboard_data()
    top5_json = json.dumps(data["top5"], ensure_ascii=False).replace("</", "<\\/")
    return render_template(
        "leaderboard.html",
        top5=data["top5"],
        top5_json=top5_json,
        total_participants=data["total_participants"],
        total_joins=data["total_joins"],
    )


@app.route("/api/leaderboard")
def api_leaderboard():
    return jsonify(get_leaderboard_data())


# ---------------------------------------------------------------
# رابط مساعد لضبط الويبهوك عند تيليجرام (تفتحه مرة وحدة بالمتصفح)
# ---------------------------------------------------------------
@app.route("/setup-webhook")
def setup_webhook():
    base_url = request.url_root.rstrip("/")
    webhook_url = f"{base_url}/webhook/{WEBHOOK_SECRET}"
    resp = requests.get(
        f"{API_URL}/setWebhook",
        params={"url": webhook_url, "allowed_updates": '["chat_member"]'},
        timeout=15,
    )
    return resp.json()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
else:
    init_db()
