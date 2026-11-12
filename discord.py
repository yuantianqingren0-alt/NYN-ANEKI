# Python 3.10+ | discord.py 2.x
# env: DISCORD_BOT_TOKEN, DISCORD_CLIENT_ID, WEB_BASE_URL, DISCORD_WEBHOOK_URL

import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN        = os.environ["DISCORD_BOT_TOKEN"]
CLIENT_ID    = os.environ["DISCORD_CLIENT_ID"]
WEB_BASE_URL = os.environ["WEB_BASE_URL"]          # e.g. https://auth-bot-web.onrender.com

ROLE_NAME = "認証済み"

intents = discord.Intents.default()
intents.members = True
intents.guilds  = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ── ロール自動作成 ──────────────────────────────────────────────────
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


# ── 既存サーバー分もカバー ──────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        await ensure_role(guild)
    await bot.tree.sync()
    print("Slash commands synced.")


# ── /auth コマンド ─────────────────────────────────────────────────
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


# ── Step 1: 「認証する」ボタン ─────────────────────────────────────
class AuthStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.primary, emoji="🔐")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # OAuth2 URLを生成 — state にユーザーIDとギルドIDを埋め込む
        state = f"{interaction.user.id}:{interaction.guild_id}"
        oauth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={WEB_BASE_URL}/callback"
            f"&response_type=code"
            f"&scope=identify%20email"
            f"&state={state}"
        )
        # 本人のみに見えるフォローアップ
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
            ephemeral=True,   # 押した本人のみに表示
        )


# ── Step 2: Webに飛ぶボタン ───────────────────────────────────────
class AuthWebView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=300)
        self.add_item(discord.ui.Button(
            label="認証ページへ進む",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="🔗",
        ))


# ── UptimeRobot用 keep-alive (workerプロセス側) ───────────────────
# web.py側でFlaskが /ping を返すのでそちらでOK


bot.run(TOKEN)
