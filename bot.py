import json
import time
import requests
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from threading import Lock

# ================= CONFIG =================
BOT_TOKEN = "8681415760:AAGRB25KwvwHeH9MtOiWh0JGsW3Q22QnWbk"
API_URL = "https://paid-sell.vercel.app/api/proxy?type=info&value={}"
ADMIN_ID = 8554863978  # Your admin ID
# =========================================

app = Flask(__name__)

# Rate limiting storage
rate_limit = {}
rate_lock = Lock()
RATE_LIMIT_SECONDS = 7

# Approved users storage (for personal use)
approved_users = set()

def load_approved_users():
    """Load approved users from file"""
    try:
        with open('approved_users.json', 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_approved_users():
    """Save approved users to file"""
    with open('approved_users.json', 'w') as f:
        json.dump(list(approved_users), f)

# Load existing approved users
approved_users = load_approved_users()

def check_rate_limit(user_id):
    """Check if user is rate limited"""
    with rate_lock:
        current_time = time.time()
        if user_id in rate_limit:
            last_request = rate_limit[user_id]
            if current_time - last_request < RATE_LIMIT_SECONDS:
                return False
        rate_limit[user_id] = current_time
        return True

def validate_phone(phone: str) -> bool:
    """Validate phone number"""
    phone = ''.join(filter(str.isdigit, phone))
    return len(phone) >= 10 and len(phone) <= 15

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
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

async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Phone number lookup command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    is_group = update.effective_chat.type in ['group', 'supergroup']
    
    # Check parameters
    if len(context.args) != 1:
        msg = await update.message.reply_text(
            "❌ **Usage:**\n/num 628123456789\n\n"
            "📌 **Example:** /num 6281809671246",
            parse_mode='Markdown'
        )
        if not is_group:
            context.application.create_task(delete_after(msg, 10))
        return
    
    # Check approval for personal chat
    if not is_group and user_id != ADMIN_ID and user_id not in approved_users:
        msg = await update.message.reply_text(
            "❌ **Not Authorized**\n\n"
            "This bot requires admin approval for personal use.\n"
            "Contact @proxyfxc to get access.\n\n"
            "✅ You can use this bot in groups freely!",
            parse_mode='Markdown'
        )
        context.application.create_task(delete_after(msg, 10))
        context.application.create_task(delete_after(update.message, 10))
        return
    
    # Rate limiting
    if not check_rate_limit(user_id):
        msg = await update.message.reply_text(
            f"⏰ **Rate Limited**\n\n"
            f"Please wait {RATE_LIMIT_SECONDS} seconds between requests.",
            parse_mode='Markdown'
        )
        if not is_group:
            context.application.create_task(delete_after(msg, 7))
            context.application.create_task(delete_after(update.message, 7))
        return
    
    phone = context.args[0]
    
    if not validate_phone(phone):
        msg = await update.message.reply_text(
            "❌ **Invalid Number**\n\n"
            "• 10-15 digits only\n"
            "• Include country code\n"
            "• Example: 628123456789",
            parse_mode='Markdown'
        )
        if not is_group:
            context.application.create_task(delete_after(msg, 10))
            context.application.create_task(delete_after(update.message, 10))
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text("🔍 **Fetching data...**", parse_mode='Markdown')
    
    try:
        # Make API request
        url = API_URL.format(phone)
        response = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        if response.status_code != 200:
            await processing_msg.edit_text(
                f"❌ **API Error**\n\n"
                f"Status: {response.status_code}\n"
                f"Please try again later.",
                parse_mode='Markdown'
            )
            if not is_group:
                context.application.create_task(delete_after(processing_msg, 10))
                context.application.create_task(delete_after(update.message, 10))
            return
        
        data = response.json()
        
        # Format result
        result_text = format_result(data, phone)
        
        # Add credit line
        result_text += f"\n\n👑 **Developer:** @proxyfxc"
        
        # Send result
        result_msg = await update.message.reply_text(
            result_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Delete processing message
        await processing_msg.delete()
        
        # Auto-delete in personal chat
        if not is_group:
            context.application.create_task(delete_after(update.message, 10))
            context.application.create_task(delete_after(result_msg, 10))
            
    except requests.exceptions.Timeout:
        await processing_msg.edit_text("❌ **Timeout**\n\nAPI request timed out. Please try again.", parse_mode='Markdown')
        if not is_group:
            context.application.create_task(delete_after(processing_msg, 10))
    except Exception as e:
        await processing_msg.edit_text(f"❌ **Error**\n\n{str(e)}", parse_mode='Markdown')
        if not is_group:
            context.application.create_task(delete_after(processing_msg, 10))

def format_result(data, phone):
    """Format API result nicely"""
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
            result += json.dumps(data, indent=2, ensure_ascii=False)
            return result
        else:
            return f"📱 **Result:**\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
    except:
        return f"📱 **Result:**\n```\n{data}\n```"

async def delete_after(message, seconds):
    """Delete message after specified seconds"""
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except:
        pass

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot status"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "🔧 **Bot Status**\n\n"
            "✅ Bot is running\n"
            f"⏰ Rate limit: {RATE_LIMIT_SECONDS}s\n"
            "👑 **Developer:** @proxyfxc",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text(
        f"🔧 **Admin Status**\n\n"
        f"✅ Bot running\n"
        f"👥 Approved users: {len(approved_users)}\n"
        f"⏰ Rate limit: {RATE_LIMIT_SECONDS}s\n"
        f"📊 Active rate limits: {len(rate_limit)}\n"
        f"👑 **Developer:** @proxyfxc",
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "request_access":
        # Send notification to admin
        user = query.from_user
        keyboard = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 **Access Request**\n\n"
                 f"User: {user.first_name}\n"
                 f"ID: `{user.id}`\n"
                 f"Username: @{user.username if user.username else 'N/A'}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        await query.edit_message_text(
            "✅ **Request Sent!**\n\n"
            "Admin has been notified. Please wait for approval.\n"
            "You will be notified once approved.",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("approve_"):
        user_id = int(query.data.split("_")[1])
        approved_users.add(user_id)
        save_approved_users()
        
        await query.edit_message_text(
            f"✅ **User Approved!**\n\n"
            f"User ID: `{user_id}` has been approved.",
            parse_mode='Markdown'
        )
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ **Access Granted!**\n\n"
                     "You can now use this bot in personal chat.\n"
                     "Use /num command to lookup numbers.\n\n"
                     "👑 **Developer:** @proxyfxc",
                parse_mode='Markdown'
            )
        except:
            pass

# Flask webhook endpoint
@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook updates"""
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return 'OK'

@app.route('/')
def index():
    return "Bot is running!"

import asyncio
import threading

def run_bot():
    """Run telegram bot in separate thread"""
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("num", num_lookup))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot
    bot_app.run_polling()

if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000)
