import os
import threading
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# 最初に環境変数を読み込む
load_dotenv()

# 環境変数が読み込まれた後に web.py をインポート
from web import app as flask_app

TOKEN        = os.environ.get("DISCORD_BOT_TOKEN", "")
CLIENT_ID    = os.environ.get("DISCORD_CLIENT_ID", "")
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "").rstrip("/")
PORT         = int(os.environ.get("PORT", 10000))
ROLE_NAME    = "認証済み"

intents = discord.Intents.default()
intents.members = True
intents.guilds  = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Flaskを別スレッドで起動 ─────────────────────────────────────
def run_flask():
    print(f"[web] starting Flask on port {PORT}")
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

# ── Botのイベント・コマンド ──────────────────────────────────────
@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_role(guild)

async def ensure_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        try:
            role = await guild.create_role(name=ROLE_NAME, colour=discord.Colour.green(), reason="認証システム自動作成")
        except Exception as e:
            print(f"[warn] role create failed: {e}")
    return role

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        try:
            await ensure_role(guild)
        except Exception as e:
            print(f"[warn] ensure_role failed: {e}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"[warn] tree sync failed: {e}")

@bot.tree.command(name="auth", description="認証パネルを表示します")
@app_commands.checks.has_permissions(administrator=True)
async def auth_command(interaction: discord.Interaction):
    view = AuthStartView()
    await interaction.response.send_message(
        embed=discord.Embed(
            title="✅ 認証",
            description="このサーバーに参加するには認証が必要です。\n\n下の **「認証する」** ボタンをタップしてください。\nタップすると **認証済み** ロールが付与されます。",
            colour=discord.Colour.blurple(),
        ),
        view=view,
    )

class AuthStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.primary, emoji="🔐")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = f"{interaction.user.id}:{interaction.guild_id}"
        oauth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={WEB_BASE_URL}/callback"
            f"&response_type=code"
            f"&scope=identify%20email"
            f"&state={state}"
        )
        view = AuthWebView(oauth_url)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌐 認証を完了してください",
                description="下のボタンから認証ページへ進んでください。\nDiscord アカウントでログインし、**カメラの共有を許可**してください。",
                colour=discord.Colour.green(),
            ),
            view=view,
            ephemeral=True,
        )

class AuthWebView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=300)
        self.add_item(discord.ui.Button(label="認証ページへ進む", style=discord.ButtonStyle.link, url=url, emoji="🔗"))

# ── 起動 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1. Flaskをバックグラウンドスレッドで起動
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. Discord Botを起動
    bot.run(TOKEN)
