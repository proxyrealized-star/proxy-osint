import os
import json
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any

import requests
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8681415760:AAFPFcK8P56CFyxOulWr69I0QLyYGwx-f1s")
API_URL = "https://num-api-nu.vercel.app/get-info?phone={num}&apikey=boss10m"

# Multiple force join channels
FORCE_CHANNELS = [
    {"username": "@backup_enc", "url": "https://t.me/+gnyODeNwEwNjZDJl"},
    {"username": "@backup4_enc", "url": "https://t.me/+oirjMZaVI543M2Y1"},
    {"username": "@esxcrows", "url": "https://t.me/esxcrows"}
]

# Flask keep-alive
FLASK_HOST = "0.0.0.0"
FLASK_PORT = int(os.getenv("PORT", 8080))

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== Database Manager (JSON) ==============
class UserDB:
    def __init__(self):
        self.data_file = "users.json"
        self.users = self._load()

    def _load(self) -> Dict:
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Load error: {e}")
        return {}

    def _save(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")

    def get_user(self, user_id: int) -> Dict:
        return self.users.get(str(user_id), {})

    def create_user(self, user_id: int, username: str = "", first_name: str = "") -> Dict:
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

    def update_user(self, user_id: int, **kwargs) -> bool:
        uid = str(user_id)
        if uid in self.users:
            self.users[uid].update(kwargs)
            self._save()
            return True
        return False

    def add_verified_channel(self, user_id: int, channel: str) -> bool:
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

# ============== Force Join Check ==============
async def check_force_join(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_data = db.get_user(user_id)
    if user_data.get("verified", False):
        return True

    all_joined = True
    newly_verified = False

    for channel in FORCE_CHANNELS:
        channel_username = channel["username"]
        if channel_username in user_data.get("verified_channels", []):
            continue

        try:
            member = await context.bot.get_chat_member(chat_id=channel_username, user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                db.add_verified_channel(user_id, channel_username)
                newly_verified = True
            else:
                all_joined = False
        except Exception as e:
            logger.warning(f"Force join check error for {channel_username}: {e}")
            all_joined = False

    if newly_verified and all_joined:
        db.update_user(user_id, verified=True)

    return all_joined


async def send_force_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for ch in FORCE_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"📢 Join {ch['username']}", url=ch["url"])])
    keyboard.append([InlineKeyboardButton("✅ I've Joined All", callback_data="verify_join")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    message = """
<b>🔒 CHANNEL SUBSCRIPTION REQUIRED</b>

To use this bot, you must join all these channels:

━━━━━━━━━━━━━━━━━━━━━
"""

    for ch in FORCE_CHANNELS:
        message += f"📢 {ch['username']}\n"

    message += """
━━━━━━━━━━━━━━━━━━━━━

<b>Steps:</b>
1️⃣ Click each button above
2️⃣ Join all channels
3️⃣ Click "I've Joined All"
4️⃣ Bot will start automatically

<i>Powered by @proxyfxc</i>
"""
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


# ============== ANIMATION FUNCTIONS ==============
async def show_loading_animation(message, text: str, duration: float = 0.5):
    """Show professional loading animation"""
    frames = [
        "🔍",
        "🔍.",
        "🔍..",
        "🔍...",
        "⏳",
        "⏳.",
        "⏳..",
        "⏳...",
        "⚙️",
        "⚙️.",
        "⚙️..",
        "⚙️...",
        "✅"
    ]
    
    for frame in frames:
        await message.edit_text(f"{frame} {text}")
        await asyncio.sleep(duration / len(frames))
    
    return message


async def show_progress_animation(message, current: int, total: int):
    """Show progress bar animation"""
    percent = int(current / total * 100)
    bar_length = 20
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    text = f"🔄 Fetching data [{bar}] {percent}%"
    await message.edit_text(text)
    await asyncio.sleep(0.05)


async def delete_with_animation(message, delay: float = 0.5):
    """Delete message with countdown animation"""
    if not message:
        return
    
    frames = ["🗑️", "🗑️.", "🗑️..", "🗑️...", "✓"]
    
    for frame in frames:
        try:
            await message.edit_text(f"{frame} Clearing...")
            await asyncio.sleep(delay / 5)
        except:
            pass
    
    try:
        await message.delete()
    except:
        pass


# ============== Bot Handlers ==============
def validate_phone(phone: str) -> bool:
    phone = ''.join(filter(str.isdigit, phone))
    return len(phone) == 10 and phone.startswith(("6", "7", "8", "9"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.create_user(user.id, user.username or "", user.first_name or "")

    if not await check_force_join(user.id, context):
        await send_force_join_message(update, context)
        return

    await update.message.reply_text(
        f"👋 <b>Welcome {user.first_name}</b>\n\n"
        "📌 <b>Usage:</b>\n"
        "<code>/num 9462254359</code>\n\n"
        "✨ <i>Professional loading animation with auto-clear</i>",
        parse_mode=ParseMode.HTML
    )


async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await check_force_join(user.id, context):
        await send_force_join_message(update, context)
        return

    if len(context.args) != 1:
        msg = await update.message.reply_text("❌ <b>Usage:</b>\n<code>/num 9462254359</code>", parse_mode=ParseMode.HTML)
        await delete_with_animation(msg)
        return

    phone = context.args[0]

    if not validate_phone(phone):
        msg = await update.message.reply_text(
            "❌ <b>Invalid Number</b>\n"
            "• 10 digits only\n"
            "• Start with 6/7/8/9",
            parse_mode=ParseMode.HTML
        )
        await delete_with_animation(msg)
        return

    # Delete user command with animation
    await delete_with_animation(update.message)

    # Show loading animation
    loading_msg = await update.message.reply_text("🔍 Initializing...")
    
    # Frame 1: Searching
    await show_loading_animation(loading_msg, "Fetching number details")
    
    try:
        # Frame 2: API Call with progress
        await loading_msg.edit_text("⚙️ Connecting to server...")
        
        r = requests.get(API_URL.format(num=phone), timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        
        # Progress animation
        for i in range(1, 6):
            await show_progress_animation(loading_msg, i, 5)
        
        if r.status_code != 200:
            await loading_msg.edit_text("❌ API Error | Please try again")
            await delete_with_animation(loading_msg)
            return

        data = r.json()

        # Handle raw response
        if isinstance(data, list):
            raw = {
                "success": True,
                "status_code": r.status_code,
                "query": phone,
                "result_count": len(data),
                "result": data
            }
        elif isinstance(data, dict):
            raw = data
        else:
            await loading_msg.edit_text("⚠️ Invalid API response")
            await delete_with_animation(loading_msg)
            return

        raw_json = json.dumps(raw, indent=4, ensure_ascii=False)

        if len(raw_json) > 4000:
            raw_json = raw_json[:4000] + "\n\n⚠️ Output truncated"

        # Final success animation
        await loading_msg.edit_text("✅ Data received | Formatting...")
        await asyncio.sleep(0.2)
        
        # Show result
        await loading_msg.edit_text(
            f"<b>📊 RESULT FOR {phone}</b>\n\n"
            f"<pre>{raw_json}</pre>\n\n"
            f"<i>✨ Auto-clearing in 2 seconds...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Auto delete after 2 seconds
        await asyncio.sleep(2)
        await delete_with_animation(loading_msg)

    except Exception as e:
        await loading_msg.edit_text(f"❌ Error: {str(e)[:100]}")
        await delete_with_animation(loading_msg)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    data = query.data

    if data == "verify_join":
        await query.edit_message_text("🔄 Verifying channel membership...")

        if await check_force_join(user.id, context):
            await query.edit_message_text("✅ <b>Verification successful!</b>\n\nUse <code>/num</code> command.", parse_mode=ParseMode.HTML)
        else:
            user_data = db.get_user(user.id)
            missing = []
            for ch in FORCE_CHANNELS:
                if ch["username"] not in user_data.get("verified_channels", []):
                    missing.append(ch["username"])

            if missing:
                text = f"❌ <b>Still missing:</b> {', '.join(missing)}\n\nPlease join all channels and try again."
                await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text("❌ Verification failed. Please join all channels and try again.")


# ============== Flask Keep-Alive ==============
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "alive", "service": "Number Lookup Bot", "time": datetime.now().isoformat()})

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot_running": True})

def run_flask():
    app.run(host=FLASK_HOST, port=FLASK_PORT)


# ============== Main ==============
def main():
    import threading

    # Start Flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask keep-alive started")

    # Start bot
    application = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("num", num_lookup))
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🤖 Bot running | Professional animations | Auto-delete | Multi-channel force join")
    application.run_polling()


if __name__ == "__main__":
    main()
