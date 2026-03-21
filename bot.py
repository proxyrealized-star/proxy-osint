import json
import requests
import time
import sqlite3
import os
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from flask import Flask, request, render_template_string, redirect, url_for, session

# ================= CONFIG =================
BOT_TOKEN = "8681415760:AAG0Yj7gFq2lcuRPXOP5FERbarzyQ_yr7P8"
ADMIN_ID = 8554863978  # Your admin ID
API_URL = "https://paid-sell.vercel.app/api/proxy?type=info&value={}"
RATE_LIMIT = 6  # seconds

# Flask setup
app = Flask(__name__)
app.secret_key = "bot_secret_key_123"
PORT = int(os.environ.get("PORT", 8080))

# Admin credentials
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
# =========================================

# ================= DATABASE =================
db = sqlite3.connect("users.db", check_same_thread=False)
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, joined_date TEXT, total_requests INTEGER DEFAULT 0)")
cur.execute("CREATE TABLE IF NOT EXISTS requests_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT, timestamp TEXT, status TEXT)")
db.commit()

def save_user(uid, username=None):
    cur.execute("SELECT id FROM users WHERE id = ?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (id, username, joined_date, total_requests) VALUES (?, ?, ?, ?)", 
                    (uid, username, datetime.now().strftime("%Y-%d-%m %H:%M:%S"), 0))
        db.commit()

def update_stats(uid, phone, status):
    cur.execute("UPDATE users SET total_requests = total_requests + 1 WHERE id = ?", (uid,))
    cur.execute("INSERT INTO requests_log (user_id, phone, timestamp, status) VALUES (?, ?, ?, ?)",
                (uid, phone, datetime.now().strftime("%Y-%d-%m %H:%M:%S"), status))
    db.commit()

def total_users():
    cur.execute("SELECT COUNT(*) FROM users")
    return cur.fetchone()[0]

def get_user_requests(uid):
    cur.execute("SELECT total_requests FROM users WHERE id = ?", (uid,))
    result = cur.fetchone()
    return result[0] if result else 0

def get_all_users():
    cur.execute("SELECT id, username, joined_date, total_requests FROM users ORDER BY joined_date DESC")
    return cur.fetchall()

def get_recent_requests(limit=20):
    cur.execute("SELECT user_id, phone, timestamp, status FROM requests_log ORDER BY timestamp DESC LIMIT ?", (limit,))
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

# ================= PHONE VALIDATION =================
def validate_phone(phone: str) -> bool:
    phone = ''.join(filter(str.isdigit, phone))
    # Indonesia numbers (62) or 10-digit numbers
    if phone.startswith("62") and len(phone) >= 10:
        return True
    return len(phone) == 10 and phone.startswith(("6", "7", "8", "9"))

# ================= API CALL =================
def fetch_phone_info(phone):
    try:
        r = requests.get(
            API_URL.format(phone),
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        
        if r.status_code != 200:
            return None, f"API Error: {r.status_code}"
        
        data = r.json()
        return data, None
        
    except requests.exceptions.Timeout:
        return None, "Request timeout"
    except requests.exceptions.ConnectionError:
        return None, "Connection error"
    except json.JSONDecodeError:
        return None, "Invalid API response"
    except Exception as e:
        return None, str(e)

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    save_user(uid, username)
    
    await update.message.reply_text(
        f"👋 Welcome {update.effective_user.first_name}!\n\n"
        f"📌 Use command:\n"
        f"/num 6281809671246\n\n"
        f"⏱️ Rate limit: {RATE_LIMIT} seconds\n"
        f"📊 Your requests: {get_user_requests(uid)}\n\n"
        f"🔗 Admin panel: /admin (web)"
    )

async def num_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username
    save_user(uid, username)
    
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
    
    # Validate phone
    if not validate_phone(clean_phone):
        await update.message.reply_text(
            "❌ Invalid number\n"
            "• Indonesia: 628xxxxxxxxx\n"
            "• India: 10 digits starting with 6/7/8/9"
        )
        update_stats(uid, phone, "invalid")
        return
    
    # Check rate limit
    allowed, wait_time = check_rate_limit(uid)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Rate limit! Please wait {wait_time} seconds before next request."
        )
        return
    
    msg = await update.message.reply_text("🔍 Fetching data...")
    
    # Make API call
    data, error = fetch_phone_info(clean_phone)
    update_last_request(uid)
    
    if error:
        await msg.edit_text(f"❌ {error}")
        update_stats(uid, phone, "failed")
        return
    
    # Format response
    raw_json = json.dumps(data, indent=4, ensure_ascii=False)
    
    # Telegram message limit
    if len(raw_json) > 4000:
        raw_json = raw_json[:4000] + "\n\n⚠️ Output truncated"
    
    await msg.edit_text(
        f"```json\n{raw_json}\n```",
        parse_mode="Markdown"
    )
    
    update_stats(uid, phone, "success")
    
    # Show remaining requests
    total_req = get_user_requests(uid)
    await update.message.reply_text(f"📊 Total requests: {total_req}")

# ================= ADMIN COMMANDS =================
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    total = total_users()
    total_req, success, failed = get_stats()
    
    await update.message.reply_text(
        f"📊 BOT STATS\n\n"
        f"👥 Total Users: {total}\n"
        f"🔍 Total Requests: {total_req}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"⏱️ Rate Limit: {RATE_LIMIT}s"
    )

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
    
    for uid, uname, joined, reqs in users:
        try:
            await context.bot.send_message(uid, f"📢 {msg}")
            sent += 1
        except:
            failed += 1
    
    await update.message.reply_text(f"✅ Sent to {sent} users\n❌ Failed: {failed}")

# ================= FLASK ROUTES =================
@app.route('/')
def home():
    return "Bot is running! Admin panel at /admin"

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USER and request.form['password'] == ADMIN_PASS:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid credentials"
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Login</title>
            <style>
                body { background: #1a1a1a; color: #fff; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; }
                .login { background: #2d2d2d; padding: 30px; border-radius: 10px; width: 300px; }
                input { width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 5px; }
                button { background: #00a86b; color: white; padding: 10px; width: 100%; border: none; border-radius: 5px; cursor: pointer; }
                h2 { text-align: center; }
            </style>
        </head>
        <body>
            <div class="login">
                <h2>Admin Login</h2>
                <form method="post">
                    <input type="text" name="username" placeholder="Username" required>
                    <input type="password" name="password" placeholder="Password" required>
                    <button type="submit">Login</button>
                </form>
            </div>
        </body>
        </html>
    ''')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    total = total_users()
    total_req, success, failed = get_stats()
    users = get_all_users()[:20]
    recent = get_recent_requests(20)
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{ background: #1a1a1a; color: #fff; font-family: Arial; padding: 20px; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
            .card {{ background: #2d2d2d; padding: 20px; border-radius: 10px; text-align: center; }}
            .card h3 {{ margin: 0; color: #00a86b; }}
            .card p {{ font-size: 24px; margin: 10px 0; }}
            table {{ width: 100%; background: #2d2d2d; border-radius: 10px; overflow: hidden; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #3d3d3d; }}
            th {{ background: #00a86b; }}
            .logout {{ background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; float: right; }}
            h1 {{ display: inline-block; }}
        </style>
    </head>
    <body>
        <h1>Admin Dashboard</h1>
        <a href="/admin/logout" class="logout">Logout</a>
        
        <div class="stats">
            <div class="card"><h3>Total Users</h3><p>{total}</p></div>
            <div class="card"><h3>Total Requests</h3><p>{total_req}</p></div>
            <div class="card"><h3>Success</h3><p>{success}</p></div>
            <div class="card"><h3>Failed</h3><p>{failed}</p></div>
        </div>
        
        <h2>Recent Users</h2>
        <table>
            <tr><th>ID</th><th>Username</th><th>Joined</th><th>Requests</th></tr>
    '''
    
    for uid, uname, joined, reqs in users:
        html += f'<tr><td>{uid}</td><td>@{uname or "N/A"}</td><td>{joined}</td><td>{reqs}</td></tr>'
    
    html += '''
        </table>
        
        <h2>Recent Requests</h2>
        <table>
            <tr><th>User ID</th><th>Phone</th><th>Time</th><th>Status</th></tr>
    '''
    
    for uid, phone, ts, status in recent:
        color = "#00a86b" if status == "success" else "#dc3545" if status == "failed" else "#ffc107"
        html += f'<tr><td>{uid}</td><td>{phone}</td><td>{ts}</td><td style="color:{color}">{status}</td></tr>'
    
    html += '''
        </table>
    </body>
    </html>
    '''
    
    return html

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

# ================= RUN BOT & FLASK =================
def run_flask():
    app.run(host='0.0.0.0', port=PORT)

def main():
    # Start Flask in thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start Telegram bot
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("num", num_lookup))
    bot_app.add_handler(CommandHandler("users", users_cmd))
    bot_app.add_handler(CommandHandler("broadcast", broadcast))
    
    print("🤖 Bot started!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"🔗 API: {API_URL}")
    print(f"⏱️ Rate limit: {RATE_LIMIT} seconds")
    print(f"🌐 Admin panel: http://localhost:{PORT}/admin")
    
    bot_app.run_polling()

if __name__ == "__main__":
    main()
