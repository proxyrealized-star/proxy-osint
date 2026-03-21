import os
import json
import asyncio
import logging
from datetime import datetime

import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8681415760:AAFPFcK8P56CFyxOulWr69I0QLyYGwx-f1s")
API_URL = "https://paid-sell.vercel.app/api/proxy?type=info&value={}"

# Force join channels
FORCE_CHANNELS = [
    {"username": "@esxcrows", "url": "https://t.me/esxcrows"},
    {"username": "@ceviety", "url": "https://t.me/ceviety"}
]

FLASK_HOST = "0.0.0.0"
FLASK_PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== Database ==============
class UserDB:
    def __init__(self):
        self.data_file = "users.json"
        self.users = self._load()

    def _load(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r") as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump(self.users, f, indent=2)
        except:
            pass

    def get_user(self, user_id: int):
        return self.users.get(str(user_id), {})

    def create_user(self, user_id: int, username: str = "", first_name: str = ""):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "joined_date": datetime.now().isoformat(),
                "verified_channels": [],
                "verified": False
            }
            self._save()
        return self.users[uid]

    def update_user(self, user_id: int, **kwargs):
        uid = str(user_id)
        if uid in self.users:
            self.users[uid].update(kwargs)
            self._save()
            return True
        return False

    def add_verified_channel(self, user_id: int, channel: str):
        uid = str(user_id)
        if uid in self.users:
            if channel not in self.users[uid].get("verified_channels", []):
                self.users[uid].setdefault("verified_channels", []).append(channel)
                self._save()
            all_verified = all(ch["username"] in self.users[uid]["verified_channels"] for ch in FORCE_CHANNELS)
            self.users[uid]["verified"] = all_verified
            self._save()
            return True
        return False


db = UserDB()

# ============== Force Join ==============
async def check_force_join(user_id: int, context) -> bool:
    user_data = db.get_user(user_id)
    if user_data.get("verified", False):
        return True

    all_joined = True
    newly = False

    for ch in FORCE_CHANNELS:
        username = ch["username"]
        if username in user_data.get("verified_channels", []):
            continue

        try:
            member = await context.bot.get_chat_member(chat_id=username, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                db.add_verified_channel(user_id, username)
                newly = True
            else:
                all_joined = False
        except:
            all_joined = False

    if newly and all_joined:
        db.update_user(user_id, verified=True)

    return all_joined


async def send_force_join(update: Update, context):
    keyboard = []
    for ch in FORCE_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"📢 Join {ch['username']}", url=ch["url"])])
    keyboard.append([InlineKeyboardButton("✅ I've Joined All", callback_data="verify")])

    msg = """
<b>🔒 CHANNELS REQUIRED</b>

Join both channels:
"""
    for ch in FORCE_CHANNELS:
        msg += f"📢 {ch['username']}\n"
    msg += "\nThen click verify."

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, 
                                   reply_markup=InlineKeyboardMarkup(keyboard))


# ============== Handlers ==============
def validate_phone(phone: str) -> bool:
    phone = ''.join(filter(str.isdigit, phone))
    return len(phone) == 10 and phone.startswith(("6", "7", "8", "9"))


async def start(update: Update, context):
    user = update.effective_user
    db.create_user(user.id, user.username or "", user.first_name or "")

    if not await check_force_join(user.id, context):
        await send_force_join(update, context)
        return

    await update.message.reply_text(
        f"👋 Welcome {user.first_name}\n\n"
        "📌 /num 9462254359",
        parse_mode=ParseMode.HTML
    )


async def num_lookup(update: Update, context):
    user = update.effective_user

    if not await check_force_join(user.id, context):
        await send_force_join(update, context)
        return

    if len(context.args) != 1:
        msg = await update.message.reply_text("❌ Usage: /num 9462254359")
        await asyncio.sleep(0.5)
        await msg.delete()
        return

    phone = context.args[0]

    if not validate_phone(phone):
        msg = await update.message.reply_text("❌ Invalid number\n10 digits only")
        await asyncio.sleep(0.5)
        await msg.delete()
        return

    # Delete command
    await asyncio.sleep(0.5)
    await update.message.delete()

    # Show loading
    loading = await update.message.reply_text("🔍 Fetching...")

    try:
        r = requests.get(API_URL.format(num=phone), timeout=15, headers={"User-Agent": "Mozilla/5.0"})

        if r.status_code != 200:
            await loading.edit_text("❌ API Error")
            await asyncio.sleep(1)
            await loading.delete()
            return

        data = r.json()

        # Format response
        if isinstance(data, list):
            raw = {"success": True, "query": phone, "result": data}
        elif isinstance(data, dict):
            raw = data
        else:
            await loading.edit_text("⚠️ Invalid response")
            await asyncio.sleep(1)
            await loading.delete()
            return

        result = json.dumps(raw, indent=4, ensure_ascii=False)
        if len(result) > 4000:
            result = result[:4000] + "\n\n⚠️ Truncated"

        # Show result
        await loading.edit_text(f"<b>Result for {phone}</b>\n\n<pre>{result}</pre>", parse_mode=ParseMode.HTML)

        # Auto delete after 2 seconds
        await asyncio.sleep(2)
        await loading.delete()

    except Exception as e:
        await loading.edit_text(f"❌ Error: {str(e)[:50]}")
        await asyncio.sleep(1)
        await loading.delete()


async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data != "verify":
        return

    user = update.effective_user
    await query.edit_message_text("🔄 Verifying...")

    if await check_force_join(user.id, context):
        await query.edit_message_text("✅ Verified!\n\nUse /num command.")
    else:
        user_data = db.get_user(user.id)
        missing = [ch["username"] for ch in FORCE_CHANNELS 
                   if ch["username"] not in user_data.get("verified_channels", [])]
        
        keyboard = [[InlineKeyboardButton(f"📢 Join {ch}", url=next(c["url"] for c in FORCE_CHANNELS if c["username"] == ch))] 
                    for ch in missing]
        keyboard.append([InlineKeyboardButton("🔄 Verify Again", callback_data="verify")])
        
        await query.edit_message_text(
            f"❌ Missing: {', '.join(missing)}\n\nJoin and click verify.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ============== Flask ==============
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

def run_flask():
    app.run(host=FLASK_HOST, port=FLASK_PORT)


# ============== Main ==============
def main():
    import threading
    threading.Thread(target=run_flask, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("num", num_lookup))
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot running...")
    application.run_polling()


if __name__ == "__main__":
    main()
