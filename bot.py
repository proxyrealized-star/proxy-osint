import json
import requests
import time
import sqlite3
import os
import threading
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request, render_template_string, redirect, url_for, session

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8681415760:AAG0Yj7gFq2lcuRPXOP5FERbarzyQ_yr7P8")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8554863978"))
DEVELOPER_USERNAME = "@proxyfxc"
API_URL = "https://paid-sell.vercel.app/api/proxy?type=info&value={}"
RATE_LIMIT = 6
RESULT_DELETE_SECONDS = 0.8

FORCE_CHANNELS = ["@ceviety", "@esxcrows"]

# Flask
app = Flask(__name__)
app.secret_key = "bot_secret_key_123"
PORT = int(os.environ.get("PORT", 8080))
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
# =========================================

# ================= DATABASE =================
db = sqlite3.connect("users.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, joined_date TEXT, total_requests INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, approved INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS group_approvals (group_id INTEGER PRIMARY KEY, group_name TEXT, approved_by INTEGER, approved_date TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS requests_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, timestamp TEXT, status TEXT, group_id INTEGER DEFAULT 0)")
db.commit()

def save_user(uid, username=None):
    cur.execute("SELECT id FROM users WHERE id = ?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (id, username, joined_date, total_requests, verified, approved) VALUES (?, ?, ?, ?, ?, ?)", 
                    (uid, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 0, 0))
        db.commit()

def set_verified(uid):
    cur.execute("UPDATE users SET verified = 1 WHERE id = ?", (uid,))
    db.commit()

def is_verified(uid):
    cur.execute("SELECT verified FROM users WHERE id = ?", (uid,))
    result = cur.fetchone()
    return result and result[0] == 1

def set_approved(uid):
    cur.execute("UPDATE users SET approved = 1 WHERE id = ?", (uid,))
    db.commit()

def revoke_approval(uid):
    cur.execute("UPDATE users SET approved = 0 WHERE id = ?", (uid,))
    db.commit()

def is_approved(uid):
    cur.execute("SELECT approved FROM users WHERE id = ?", (uid,))
    result = cur.fetchone()
    return result and result[0] == 1

def update_stats(uid, phone, status, group_id=0):
    cur.execute("UPDATE users SET total_requests = total_requests + 1 WHERE id = ?", (uid,))
    cur.execute("INSERT INTO requests_log (user_id, phone, timestamp, status, group_id) VALUES (?, ?, ?, ?, ?)",
                (uid, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, group_id))
    db.commit()

def total_users():
    cur.execute("SELECT COUNT(*) FROM users")
    return cur.fetchone()[0]

def is_group_approved(group_id):
    cur.execute("SELECT group_id FROM group_approvals WHERE group_id = ?", (group_id,))
    return cur.fetchone() is not None

def approve_group(group_id, group_name):
    cur.execute("INSERT OR IGNORE INTO group_approvals (group_id, group_name, approved_by, approved_date) VALUES (?, ?, ?, ?)",
                (group_id, group_name, ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()

def get_all_users():
    cur.execute("SELECT id, username, joined_date, total_requests, verified, approved FROM users ORDER BY joined_date DESC")
    return cur.fetchall()

def get_pending_users():
    cur.execute("SELECT id, username, joined_date FROM users WHERE verified = 1 AND approved = 0 ORDER BY joined_date DESC")
    return cur.fetchall()

def get_stats():
    total_req = cur.execute("SELECT COUNT(*) FROM requests_log").fetchone()[0]
    success = cur.execute("SELECT COUNT(*) FROM requests_log WHERE status = 'success'").fetchone()[0]
    failed = cur.execute("SELECT COUNT(*) FROM requests_log WHERE status = 'failed'").fetchone()[0]
    return total_req, success, failed

# ================= RATE LIMIT =================
last_request = {}

def check_rate_limit(user_id):
    now = time.time()
    if user_id in last_request:
        elapsed = now - last_request[user_id]
        if elapsed < RATE_LIMIT:
            return False, round(RATE_LIMIT - elapsed, 1)
    return True, 0

def update_last_request(user_id):
    last_request[user_id] = time.time()

# ================= FORCE JOIN =================
async def is_joined(bot, user_id):
    for ch in FORCE_CHANNELS:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def join_kb():
    btns = []
    for ch in FORCE_CHANNELS:
        btns.append([InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch[1:]}")])
    btns.append([InlineKeyboardButton("✅ Verify", callback_data="verify"]))
    return InlineKeyboardMarkup(btns)

def contact_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 CONTACT DEVELOPER", url=f"https://t.me/{DEVELOPER_USERNAME[1:]}")],
        [InlineKeyboardButton("🔄 Check Status", callback_data="check_status")]
    ])

def approved_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Start Analysis", callback_data="start_analysis")],
        [InlineKeyboardButton("📞 Contact Support", url=f"https://t.me/{DEVELOPER_USERNAME[1:]}")]
    ])

def group_contact_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 CONTACT ADMIN", url=f"https://t.me/{DEVELOPER_USERNAME[1:]}")]
    ])

# ================= API =================
def fetch_phone_info(phone):
    try:
        r = requests.get(API_URL.format(phone), timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, f"API Error: {r.status_code}"
        data = r.json()
        
        if data.get("success") and data.get("data"):
            info = data["data"]
            formatted = f"""
╔══════════════════════════════════════╗
║     📱 PHONE NUMBER INFO PRO         ║
║           BY {DEVELOPER_USERNAME}            ║
╚══════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 MOBILE: {info.get('mobile', 'N/A')}
👤 NAME: {info.get('name', 'N/A')}
👨 FATHER: {info.get('father_name', 'N/A')}
📍 ADDRESS: {info.get('address', 'N/A')}
📱 ALT MOBILE: {info.get('alt_mobile', 'N/A')}
🔄 CIRCLE: {info.get('circle', 'N/A')}
📧 EMAIL: {info.get('email', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💻 DEVELOPER: {DEVELOPER_USERNAME}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            return formatted, None
        return None, "No data found"
    except Exception as e:
        return None, str(e)

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    save_user(uid, username)
    
    # Group chat
    if update.effective_chat.type in ["group", "supergroup"]:
        if not is_group_approved(update.effective_chat.id):
            await update.message.reply_text(
                f"❌ This group is not approved.\n\n📞 Contact {DEVELOPER_USERNAME} for approval.",
                reply_markup=group_contact_kb()
            )
            return
        await update.message.reply_text(
            f"✅ Group approved! Use /num 6281809671246"
        )
        return
    
    # Private chat
    # Check if already approved
    if is_approved(uid):
        await update.message.reply_text(
            f"✅ Welcome back! You have full access.\n\n"
            f"📌 Use: /num 6281809671246\n"
            f"📊 Requests: {cur.execute('SELECT total_requests FROM users WHERE id=?', (uid,)).fetchone()[0]}"
        )
        return
    
    # Check if verified channels
    if await is_joined(context.bot, uid):
        set_verified(uid)
        await update.message.reply_text(
            f"✅ Channels Verified!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 To get access, contact developer:\n"
            f"{DEVELOPER_USERNAME}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Click the button below to contact:",
            reply_markup=contact_kb()
        )
    else:
        await update.message.reply_text(
            "🔒 **ACCESS REQUIRED**\n\n"
            "Please join the following channels to verify yourself:\n\n"
            "After joining, click **VERIFY** button.",
            reply_markup=join_kb(),
            parse_mode="Markdown"
        )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if query.data == "verify":
        if await is_joined(context.bot, uid):
            set_verified(uid)
            await query.message.edit_text(
                f"✅ **Verification Successful!**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 **To get access, contact developer:**\n"
                f"{DEVELOPER_USERNAME}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Click the button below to contact:",
                reply_markup=contact_kb(),
                parse_mode="Markdown"
            )
        else:
            await query.message.edit_text(
                "❌ You haven't joined all channels yet.\n\n"
                "Please join and click **VERIFY** again.",
                reply_markup=join_kb()
            )
    
    elif query.data == "check_status":
        if is_approved(uid):
            await query.message.edit_text(
                f"✅ **Access Granted!**\n\n"
                f"Now you can use:\n"
                f"/num 6281809671246\n\n"
                f"📊 Total requests: {cur.execute('SELECT total_requests FROM users WHERE id=?', (uid,)).fetchone()[0]}",
                reply_markup=approved_kb()
            )
        else:
            await query.message.edit_text(
                f"⏳ **Pending Approval**\n\n"
                f"Your request has been sent to {DEVELOPER_USERNAME}\n"
                f"Please wait for approval.\n\n"
                f"Contact: {DEVELOPER_USERNAME}"
            )
    
    elif query.data == "start_analysis":
        await query.message.reply_text(
            "🔍 Send phone number:\n"
            "/num 6281809671246"
        )

async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    chat_id = update.effective_chat.id
    is_group = update.effective_chat.type in ["group", "supergroup"]
    
    save_user(uid, username)
    
    # Group check
    if is_group:
        if not is_group_approved(chat_id):
            await update.message.reply_text(
                f"❌ This group is not approved.\n\nContact {DEVELOPER_USERNAME}",
                reply_markup=group_contact_kb()
            )
            return
    else:
        # Private chat - check approval
        if not is_approved(uid):
            await update.message.reply_text(
                f"❌ **Access Denied**\n\n"
                f"You are not approved to use this bot.\n\n"
                f"Contact {DEVELOPER_USERNAME} to get access.\n\n"
                f"Use /start to check status.",
                parse_mode="Markdown",
                reply_markup=contact_kb()
            )
            return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ Usage:\n/num 6281809671246\n\n"
            "Examples:\n"
            "• Indonesia: 628123456789\n"
            "• India: 9876543210"
        )
        return
    
    phone = context.args[0].strip()
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    if not (clean_phone.startswith("62") and len(clean_phone) >= 10) and not (len(clean_phone) == 10 and clean_phone.startswith(("6", "7", "8", "9"))):
        await update.message.reply_text("❌ Invalid number\n• Indonesia: 628xxxxxxxxx\n• India: 10 digits")
        update_stats(uid, phone, "invalid", chat_id if is_group else 0)
        return
    
    allowed, wait_time = check_rate_limit(uid)
    if not allowed:
        await update.message.reply_text(f"⏳ Please wait {wait_time} seconds.")
        return
    
    msg = await update.message.reply_text("🔍 Fetching data...")
    update_last_request(uid)
    
    try:
        await update.message.delete()
    except:
        pass
    
    result, error = fetch_phone_info(clean_phone)
    
    if error:
        await msg.edit_text(f"❌ {error}")
        update_stats(uid, phone, "failed", chat_id if is_group else 0)
        return
    
    await msg.edit_text(result, parse_mode="Markdown")
    update_stats(uid, phone, "success", chat_id if is_group else 0)
    
    async def delete_msg():
        await asyncio.sleep(RESULT_DELETE_SECONDS)
        try:
            await msg.delete()
        except:
            pass
    
    asyncio.create_task(delete_msg())

# ================= ADMIN COMMANDS =================
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approve user_id")
        return
    
    try:
        user_id = int(context.args[0])
        set_approved(user_id)
        await update.message.reply_text(f"✅ User {user_id} approved successfully!")
        
        try:
            await context.bot.send_message(user_id, "✅ **ACCESS GRANTED!**\n\nYou can now use /num command.\n\nSend: /num 6281809671246", parse_mode="Markdown")
        except:
            pass
    except:
        await update.message.reply_text("❌ Invalid user ID")

async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /revoke user_id")
        return
    
    try:
        user_id = int(context.args[0])
        revoke_approval(user_id)
        await update.message.reply_text(f"✅ User {user_id} approval revoked!")
    except:
        await update.message.reply_text("❌ Invalid user ID")

async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    users = get_pending_users()
    if not users:
        await update.message.reply_text("No pending approvals.")
        return
    
    msg = "📋 **PENDING APPROVALS:**\n\n"
    for uid, uname, date in users:
        msg += f"• ID: `{uid}` | @{uname or 'N/A'} | Joined: {date}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def approvegroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approvegroup -100123456789 group_name")
        return
    
    try:
        group_id = int(context.args[0])
        group_name = " ".join(context.args[1:]) if len(context.args) > 1 else "Unknown"
        approve_group(group_id, group_name)
        await update.message.reply_text(f"✅ Group {group_id} approved!")
    except:
        await update.message.reply_text("❌ Invalid group ID")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    total = total_users()
    total_req, success, failed = get_stats()
    verified = cur.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
    approved = cur.execute("SELECT COUNT(*) FROM users WHERE approved=1").fetchone()[0]
    groups = cur.execute("SELECT group_id, group_name FROM group_approvals").fetchall()
    
    msg = f"📊 **BOT STATS**\n\n👥 Total Users: {total}\n✅ Verified: {verified}\n⭐ Approved: {approved}\n🔍 Requests: {total_req}\n✅ Success: {success}\n❌ Failed: {failed}\n\n✅ **Approved Groups:**\n"
    for gid, gname in groups:
        msg += f"• {gname} (`{gid}`)\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast message")
        return
    
    msg = " ".join(context.args)
    users = get_all_users()
    sent = 0
    failed = 0
    
    for uid, uname, joined, reqs, verified, approved in users:
        try:
            await context.bot.send_message(uid, f"📢 {msg}")
            sent += 1
        except:
            failed += 1
    
    await update.message.reply_text(f"✅ Sent to {sent} users\n❌ Failed: {failed}")

# ================= FLASK =================
@app.route('/')
def home():
    return "Bot is running! Admin panel at /admin"

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USER and request.form['password'] == ADMIN_PASS:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        return "Invalid credentials"
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head><title>Admin Login</title>
        <style>
            body{background:#1a1a1a;color:#fff;font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;}
            .login{background:#2d2d2d;padding:30px;border-radius:10px;width:300px;}
            input{width:100%;padding:10px;margin:10px 0;border:none;border-radius:5px;}
            button{background:#00a86b;color:white;padding:10px;width:100%;border:none;border-radius:5px;cursor:pointer;}
        </style>
        </head>
        <body>
            <div class="login"><h2>Admin Login</h2>
            <form method="post">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form></div>
        </body>
        </html>
    ''')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    total = total_users()
    total_req, success, failed = get_stats()
    verified = cur.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0]
    approved = cur.execute("SELECT COUNT(*) FROM users WHERE approved=1").fetchone()[0]
    users = get_all_users()[:20]
    pending = get_pending_users()
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><title>Admin Dashboard</title>
    <style>
        body{{background:#1a1a1a;color:#fff;font-family:Arial;padding:20px;}}
        .stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:20px;margin-bottom:30px;}}
        .card{{background:#2d2d2d;padding:20px;border-radius:10px;text-align:center;}}
        .card h3{{margin:0;color:#00a86b;}}
        .card p{{font-size:24px;margin:10px 0;}}
        table{{width:100%;background:#2d2d2d;border-radius:10px;overflow:hidden;margin-top:20px;}}
        th,td{{padding:12px;text-align:left;border-bottom:1px solid #3d3d3d;}}
        th{{background:#00a86b;}}
        .logout{{background:#dc3545;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;float:right;}}
        h1{{display:inline-block;}}
        .approved{{color:#00a86b;}}
        .pending{{color:#ffc107;}}
    </style>
    </head>
    <body>
        <h1>Admin Dashboard</h1>
        <a href="/admin/logout" class="logout">Logout</a>
        <div class="stats">
            <div class="card"><h3>Users</h3><p>{total}</p></div>
            <div class="card"><h3>Verified</h3><p>{verified}</p></div>
            <div class="card"><h3>Approved</h3><p>{approved}</p></div>
            <div class="card"><h3>Requests</h3><p>{total_req}</p></div>
            <div class="card"><h3>Success</h3><p>{success}</p></div>
        </div>
        <h2>Pending Approvals ({len(pending)})</h2>
        表
            <tr><th>ID</th><th>Username</th><th>Joined</th><th>Action</th></tr>
    '''
    for uid, uname, date in pending:
        html += f'<tr><td>{uid}</td><td>@{uname or "N/A"}</td><td>{date}</td><td><a href="/admin/approve/{uid}" style="color:#00a86b;">Approve</a></td></tr>'
    
    html += f'''
        </table>
        <h2>Recent Users</h2>
        <table>
            <tr><th>ID</th><th>Username</th><th>Joined</th><th>Requests</th><th>Status</th></tr>
    '''
    for uid, uname, joined, reqs, ver, app in users:
        status = "✅ Approved" if app else ("🟡 Verified" if ver else "🔴 Pending")
        html += f'<tr><td>{uid}</td><td>@{uname or "N/A"}</td><td>{joined}</td><td>{reqs}</td><td>{status}</td></tr>'
    
    html += '</table></body></html>'
    return html

@app.route('/admin/approve/<int:user_id>')
def admin_approve(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    set_approved(user_id)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

# ================= RUN =================
def run_flask():
    app.run(host='0.0.0.0', port=PORT)

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("num", num_lookup))
    bot_app.add_handler(CommandHandler("approve", approve_cmd))
    bot_app.add_handler(CommandHandler("revoke", revoke_cmd))
    bot_app.add_handler(CommandHandler("pending", pending_cmd))
    bot_app.add_handler(CommandHandler("approvegroup", approvegroup_cmd))
    bot_app.add_handler(CommandHandler("users", users_cmd))
    bot_app.add_handler(CommandHandler("broadcast", broadcast))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🤖 Bot started!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"🔗 Force Channels: {FORCE_CHANNELS}")
    print(f"🌐 Admin panel: http://localhost:{PORT}/admin")
    
    bot_app.run_polling()

if __name__ == "__main__":
    main()
