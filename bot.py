# Python 3.10+ | discord.py 2.x
import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

TOKEN        = os.environ["DISCORD_BOT_TOKEN"]
CLIENT_ID    = os.environ["DISCORD_CLIENT_ID"]
WEB_BASE_URL = os.environ["WEB_BASE_URL"]
PORT         = int(os.environ.get("PORT", 10000))  # Renderが注入するポート

ROLE_NAME = "認証済み"

intents = discord.Intents.default()
intents.members = True
intents.guilds  = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ── ヘルスチェック用HTTPサーバー ──────────────────────────────────
async def health(request):
    return web.Response(text="OK")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[health] listening on 0.0.0.0:{PORT}")


# ── 以下、既存のイベント・コマンド ───────────────────────────────
@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_role(guild)

async def ensure_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=ROLE_NAME,
            colour=discord.Colour.green(),
            reason="認証システム自動作成",
        )
    return role

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        await ensure_role(guild)
    await bot.tree.sync()
    print("Slash commands synced.")

@bot.tree.command(name="auth", description="認証パネルを表示します")
@app_commands.checks.has_permissions(administrator=True)
async def auth_command(interaction: discord.Interaction):
    view = AuthStartView()
    await interaction.response.send_message(
        embed=discord.Embed(
            title="✅ 認証",
            description=(
                "このサーバーに参加するには認証が必要です。\n\n"
                "下の **「認証する」** ボタンをタップしてください。\n"
                "タップすると **認証済み** ロールが付与されます。"
            ),
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
                description=(
                    "下のボタンから認証ページへ進んでください。\n"
                    "Discord アカウントでログインし、**メールアドレスの共有を許可**してください。"
                ),
                colour=discord.Colour.green(),
            ),
            view=view,
            ephemeral=True,
        )

class AuthWebView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=300)
        self.add_item(discord.ui.Button(
            label="認証ページへ進む",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="🔗",
        ))


# ── 起動 ──────────────────────────────────────────────────────────
async def main():
    await start_health_server()   # 先にポートを開く
    await bot.start(TOKEN)        # その後Discordに接続

if __name__ == "__main__":
    asyncio.run(main())
