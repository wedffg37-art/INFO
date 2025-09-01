import discord
from discord.ext import commands, tasks
from flask import Flask
import threading
import os
import asyncio
import aiohttp

# --- Flask Keep-Alive ---
app = Flask(__name__)
bot_name = "Loading..."
ALLOWED_CHANNEL_ID = 1406848032070176788  # القناة المسموح بها فقط

@app.route("/")
def home():
    return f"Bot {bot_name} is operational"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Discord Bot Setup ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Missing DISCORD_BOT_TOKEN in environment variables")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.user_languages = {}
        self.DEFAULT_LANG = "en"
        self.session = None

    async def setup_hook(self):
        # إنشاء جلسة aiohttp واحدة
        self.session = aiohttp.ClientSession()
        # بدء Flask في Thread منفصل
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("🚀 Flask server started in background")
        # بدء المهام الدورية
        self.update_status.start()
        self.keep_alive.start()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    # --- Keep-Alive ---
    @tasks.loop(minutes=1)
    async def keep_alive(self):
        if self.session:
            try:
                url = "https://info-skmj.onrender.com"
                async with self.session.get(url) as response:
                    print(f"💡 Keep-Alive ping status: {response.status}")
            except Exception as e:
                print(f"⚠️ Keep-Alive error: {e}")

    @keep_alive.before_loop
    async def before_keep_alive(self):
        await self.wait_until_ready()

    # --- تحديث الحالة ---
    @tasks.loop(minutes=5)
    async def update_status(self):
        try:
            activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers")
            await self.change_presence(activity=activity)
        except Exception as e:
            print(f"⚠️ Status update failed: {e}")

    @update_status.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()

    # --- Utilities ---
    async def is_channel_allowed(self, ctx):
        return ctx.channel.id == ALLOWED_CHANNEL_ID

    async def check_ban(self, uid):
        if not self.session:
            print("⚠️ Session not initialized for check_ban")
            return None
        api_url = f"http://raw.thug4ff.com/check_ban/{uid}"
        try:
            async with self.session.get(api_url) as response:
                if response.status != 200:
                    return None
                res_json = await response.json()
                if res_json.get("status") != 200:
                    return None
                info = res_json.get("data", {})
                return {
                    "is_banned": info.get("is_banned", 0),
                    "nickname": info.get("nickname", ""),
                    "period": info.get("period", 0),
                    "region": info.get("region", "N/A")
                }
        except Exception as e:
            print(f"⚠️ Error in check_ban: {e}")
            return None

    # --- حذف الرسائل غير المرغوب فيها ---
    async def on_message(self, message):
        if message.author.bot:
            return

        # السماح فقط بالأوامر في القناة المسموح بها
        if message.channel.id == ALLOWED_CHANNEL_ID:
            if not message.content.startswith("!ID") and not message.content.startswith("!lang"):
                try:
                    await message.delete()
                    print(f"🗑️ Deleted message from {message.author} in {message.channel}")
                except discord.Forbidden:
                    print(f"⚠️ Missing permissions to delete message in {message.channel}")
                except discord.HTTPException as e:
                    print(f"⚠️ Failed to delete message: {e}")
                return

        await self.process_commands(message)

# --- Bot Commands ---
bot = MyBot()

@bot.command(name="lang")
async def change_language(ctx, lang_code: str):
    lang_code = lang_code.lower()
    if lang_code not in ["en", "fr"]:
        await ctx.send("❌ Invalid language. Available: `en`, `fr`")
        return
    bot.user_languages[ctx.author.id] = lang_code
    message = "✅ Language set to English." if lang_code == 'en' else "✅ Langue définie sur le français."
    await ctx.send(f"{ctx.author.mention} {message}")

@bot.command(name="ID")
async def check_ban_command(ctx):
    # تحقق من القناة المسموح بها
    if not await bot.is_channel_allowed(ctx):
        embed = discord.Embed(
            title="⚠️ Command Not Allowed",
            description=f"This command is only allowed in <#{ALLOWED_CHANNEL_ID}>",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    user_id = ctx.message.content[3:].strip()
    lang = bot.user_languages.get(ctx.author.id, bot.DEFAULT_LANG)

    if not user_id.isdigit():
        msg = {
            "en": f"{ctx.author.mention} ❌ **Invalid UID!**",
            "fr": f"{ctx.author.mention} ❌ **UID invalide !**"
        }
        await ctx.send(msg[lang])
        return

    ban_status = await bot.check_ban(user_id)
    if not ban_status:
        msg = {
            "en": f"{ctx.author.mention} ❌ Could not get information. Please try again later.",
            "fr": f"{ctx.author.mention} ❌ Impossible d'obtenir les informations. Veuillez réessayer plus tard."
        }
        await ctx.send(msg[lang])
        return

    is_banned = int(ban_status.get("is_banned", 0))
    period = ban_status.get("period", "N/A")
    nickname = ban_status.get("nickname", "NA")
    region = ban_status.get("region", "N/A")

    embed = discord.Embed(
        color=0xFF0000 if is_banned else 0x00FF00,
        timestamp=ctx.message.created_at
    )

    # --- معالجة حالة الحظر ---
    if is_banned:
        period_code = int(period) if str(period).isdigit() else 0
        if lang == "en":
            if period_code == 1:
                period_text = "1 month"
            elif period_code == 2:
                period_text = "2 months"
            elif period_code == 3:
                period_text = "3 months"
            elif period_code == 6:
                period_text = "6 months"
            elif period_code > 6:
                period_text = "Banned for more than 6 months"
            else:
                period_text = f"{period_code} months"
        else:  # French
            if period_code == 1:
                period_text = "1 mois"
            elif period_code == 2:
                period_text = "2 mois"
            elif period_code == 3:
                period_text = "3 mois"
            elif period_code == 6:
                period_text = "6 mois"
            elif period_code > 6:
                period_text = "Ce compte est banni depuis plus de 6 mois"
            else:
                period_text = f"{period_code} mois"

        embed.title = "**▌ Banned Account 🛑 **" if lang == "en" else "**▌ Compte banni 🛑 **"
        embed.description = (
            f"**• {'Reason' if lang=='en' else 'Raison'}:** This account used cheats.\n"
            f"**• {'Nickname' if lang=='en' else 'Pseudo'}:** {nickname}\n"
            f"**• {'Region' if lang=='en' else 'Région'}:** {region}"
        )
        embed.set_image(url="https://i.ibb.co/P7GwMDd/BANNED.png")
    else:
        embed.title = "**▌ Clean Account ✅ **" if lang == "en" else "**▌ Compte non banni ✅ **"
        embed.description = (
            f"**• {'Status' if lang=='en' else 'Statut'}:** No evidence of cheats.\n"
            f"**• {'Nickname' if lang=='en' else 'Pseudo'}:** {nickname}\n"
            f"**• {'Region' if lang=='en' else 'Région'}:** {region}"
        )
        embed.set_image(url="https://i.ibb.co/Z1KYSWp5/NOT-BANNED.png")

    embed.set_footer(text="📌 Garena Free Fire")
    embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    await ctx.send(embed=embed)

# --- Run Bot ---
async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())



