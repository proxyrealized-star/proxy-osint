import os
import json
import time
import asyncio
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes,
    CallbackQueryHandler
)
from threading import Lock
import threading

# ================= CONFIG =================
# Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8681415760:AAGRB25KwvwHeH9MtOiWh0JGsW3Q22QnWbk")
API_URL = os.environ.get("API_URL", "https://paid-sell.vercel.app/api/proxy?type=info&value={}")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8554863978"))
RATE_LIMIT_SECONDS = int(os.environ.get("RATE_LIMIT_SECONDS", "7"))
AUTO_DELETE_SECONDS = int(os.environ.get("AUTO_DELETE_SECONDS", "10"))
PORT = int(os.environ.get("PORT", "5000"))
# =========================================

app = Flask(__name__)

# Rate limiting storage
rate_limit = {}
rate_lock = Lock()

# Approved users storage
approved_users = set()

def load_approved_users():
    try:
        with open('approved_users.json', 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_approved_users():
    try:
        with open('approved_users.json', 'w') as f:
            json.dump(list(approved_users), f)
    except:
        pass

approved_users = load_approved_users()

def check_rate_limit(user_id):
    with rate_lock:
        current_time = time.time()
        if user_id in rate_limit:
            last_request = rate_limit[user_id]
            if current_time - last_request < RATE_LIMIT_SECONDS:
                return False
        rate_limit[user_id] = current_time
        return True

def validate_phone(phone: str) -> bool:
    phone = ''.join(filter(str.isdigit, phone))
    return len(phone) >= 10 and len(phone) <= 15

async def delete_after(message, seconds):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id != ADMIN_ID and user_id not in approved_users:
        keyboard = [[InlineKeyboardButton("📞 Request Access", callback_data="request_access")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 Welcome {user.first_name}\n\n"
            f"⚠️ **This bot is private**\n"
            f"Contact @proxyfxc for approval\n\n"
            f"✅ **Group users** can use freely\n"
            f"❌ **Personal chat** needs approval",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}\n\n"
        f"📌 **Commands:**\n"
        f"/num 628123456789 - Lookup phone number\n"
        f"/status - Check bot status\n\n"
        f"👑 **Developer:** @proxyfxc",
        parse_mode='Markdown'
    )

def format_result(data, phone):
    try:
        if isinstance(data, dict):
            result = f"📱 **Phone Lookup Result**\n"
            result += f"🔍 **Number:** `{phone}`\n"
            result += f"{'─' * 30}\n"
            
            for key, value in data.items():
                if value:
                    result += f"**{key.replace('_', ' ').title()}:** {value}\n"
            
            return result
        elif isinstance(data, list):
            result = f"📱 **Phone Lookup Result**\n"
            result += f"🔍 **Number:** `{phone}`\n"
            result += f"{'─' * 30}\n"
            result += json.dumps(data, indent=2, ensure_ascii=False)[:3000]
            return result
        else:
            return f"📱 **Result:**\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)[:3000]}\n```"
    except:
        return f"📱 **Result:**\n```\n{str(data)[:3000]}\n```"

async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_group = update.effective_chat.type in ['group', 'supergroup']
    
    if len(context.args) != 1:
        msg = await update.message.reply_text(
            "❌ **Usage:**\n/num 628123456789\n\n"
            "📌 **Example:** /num 6281809671246",
            parse_mode='Markdown'
        )
        if not is_group:
            asyncio.create_task(delete_after(msg, AUTO_DELETE_SECONDS))
            asyncio.create_task(delete_after(update.message, AUTO_DELETE_SECONDS))
        return
    
    if not is_group and user_id != ADMIN_ID and user_id not in approved_users:
        msg = await update.message.reply_text(
            "❌ **Not Authorized**\n\n"
            "Contact @proxyfxc for approval",
            parse_mode='Markdown'
        )
        asyncio.create_task(delete_after(msg, AUTO_DELETE_SECONDS))
        asyncio.create_task(delete_after(update.message, AUTO_DELETE_SECONDS))
        return
    
    if not check_rate_limit(user_id):
        msg = await update.message.reply_text(
            f"⏰ **Rate Limited**\n\nPlease wait {RATE_LIMIT_SECONDS} seconds",
            parse_mode='Markdown'
        )
        if not is_group:
            asyncio.create_task(delete_after(msg, AUTO_DELETE_SECONDS))
            asyncio.create_task(delete_after(update.message, AUTO_DELETE_SECONDS))
        return
    
    phone = context.args[0]
    
    if not validate_phone(phone):
        msg = await update.message.reply_text(
            "❌ **Invalid Number**\n\n10-15 digits only",
            parse_mode='Markdown'
        )
        if not is_group:
            asyncio.create_task(delete_after(msg, AUTO_DELETE_SECONDS))
            asyncio.create_task(delete_after(update.message, AUTO_DELETE_SECONDS))
        return
    
    processing_msg = await update.message.reply_text("🔍 **Fetching data...**", parse_mode='Markdown')
    
    try:
        url = API_URL.format(phone)
        response = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"
        })
        
        if response.status_code != 200:
            await processing_msg.edit_text("❌ **API Error**", parse_mode='Markdown')
            if not is_group:
                asyncio.create_task(delete_after(processing_msg, AUTO_DELETE_SECONDS))
            return
        
        data = response.json()
        result_text = format_result(data, phone)
        result_text += f"\n\n👑 **Developer:** @proxyfxc"
        
        result_msg = await update.message.reply_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        await processing_msg.delete()
        
        if not is_group:
            asyncio.create_task(delete_after(update.message, AUTO_DELETE_SECONDS))
            asyncio.create_task(delete_after(result_msg, AUTO_DELETE_SECONDS))
            
    except Exception as e:
        await processing_msg.edit_text(f"❌ **Error:** {str(e)[:100]}", parse_mode='Markdown')
        if not is_group:
            asyncio.create_task(delete_after(processing_msg, AUTO_DELETE_SECONDS))

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"🔧 **Bot Status**\n\n✅ Running\n⏰ Rate: {RATE_LIMIT_SECONDS}s\n👑 @proxyfxc",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text(
        f"🔧 **Admin Status**\n\n"
        f"✅ Bot running\n"
        f"👥 Approved: {len(approved_users)}\n"
        f"⏰ Rate limit: {RATE_LIMIT_SECONDS}s\n"
        f"👑 @proxyfxc",
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "request_access":
        user = query.from_user
        keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 **Access Request**\n\nUser: {user.first_name}\nID: `{user.id}`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        await query.edit_message_text(
            "✅ **Request Sent!**\nAdmin will approve soon.",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("approve_"):
        user_id = int(query.data.split("_")[1])
        approved_users.add(user_id)
        save_approved_users()
        
        await query.edit_message_text(f"✅ User `{user_id}` approved!", parse_mode='Markdown')
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ **Access Granted!**\nYou can now use /num command.\n\n👑 @proxyfxc",
                parse_mode='Markdown'
            )
        except:
            pass

@app.route('/')
def index():
    return "Bot is running! ✅"

def run_bot():
    """Run bot with polling"""
    print("🤖 Starting bot...")
    
    # Create application
    app_bot = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("num", num_lookup))
    app_bot.add_handler(CommandHandler("status", status))
    app_bot.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot with polling
    print("✅ Bot is polling...")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    print("🚀 Starting...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"⏰ Rate limit: {RATE_LIMIT_SECONDS}s")
    
    # Run bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run Flask server
    app.run(host='0.0.0.0', port=PORT)
