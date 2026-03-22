import json
import time
import requests
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = "8681415760:AAGRB25KwvwHeH9MtOiWh0JGsW3Q22QnWbk"
API_URL = "https://paid-sell.vercel.app/api/proxy?type=info&value={}"
ADMIN_ID = 8554863978

RATE_LIMIT = 7  # seconds
DELETE_TIME = 10  # seconds

# =========================================

app_flask = Flask(__name__)

# Store user approvals & rate limit
approved_users = set()
last_used = {}

# ================= FUNCTIONS =================

def validate_phone(phone: str) -> bool:
    phone = ''.join(filter(str.isdigit, phone))
    return len(phone) >= 10


def is_rate_limited(user_id):
    now = time.time()
    if user_id in last_used:
        if now - last_used[user_id] < RATE_LIMIT:
            return True
    last_used[user_id] = now
    return False


async def auto_delete(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass


# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # PRIVATE CHAT → NEED APPROVAL
    if update.effective_chat.type == "private":
        if user.id not in approved_users:
            await update.message.reply_text(
                "⛔ Access Pending Approval\n"
                "Wait for admin approval."
            )

            # Notify admin
            await context.bot.send_message(
                ADMIN_ID,
                f"🔔 New User Request\n\n"
                f"ID: {user.id}\n"
                f"Name: {user.first_name}"
            )
            return

    await update.message.reply_text(
        "✅ Bot Active\n\nUse:\n/num 9876543210"
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /approve USER_ID")
        return

    user_id = int(context.args[0])
    approved_users.add(user_id)

    await update.message.reply_text(f"✅ Approved: {user_id}")


async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Private approval check
    if update.effective_chat.type == "private":
        if user_id not in approved_users:
            await update.message.reply_text("⛔ Not Approved")
            return

    # Rate limit
    if is_rate_limited(user_id):
        await update.message.reply_text(
            f"⏳ Rate limit: Try after {RATE_LIMIT} sec"
        )
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage:\n/num 9876543210")
        return

    phone = context.args[0]

    if not validate_phone(phone):
        await update.message.reply_text("❌ Invalid Number")
        return

    msg = await update.message.reply_text("🔍 Fetching...")

    try:
        r = requests.get(API_URL.format(phone), timeout=15)

        if r.status_code != 200:
            await msg.edit_text("❌ API Error")
            return

        data = r.json()

        raw_json = json.dumps(data, indent=2)

        if len(raw_json) > 3500:
            raw_json = raw_json[:3500] + "\n⚠️ Truncated"

        # Inline Button
        keyboard = [
            [InlineKeyboardButton("📢 @proxyfxc", url="https://t.me/proxyfxc")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"```\n{raw_json}\n```\n\n"
            f"🔻 Credit: @proxyfxc"
        )

        sent = await msg.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

        # Auto delete
        threading.Thread(
            target=lambda: time.sleep(DELETE_TIME) or sent.delete()
        ).start()

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


# ================= MAIN =================

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("num", num_lookup))

    print("🤖 Bot Running...")
    app.run_polling()


@app_flask.route('/')
def home():
    return "Bot is running!"


if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app_flask.run(host="0.0.0.0", port=5000)
