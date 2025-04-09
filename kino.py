import os
import sqlite3
import logging
from datetime import datetime
from collections import defaultdict
from telebot import TeleBot, types
from telebot.util import quick_markup
from dotenv import load_dotenv
from flask import Flask, request
import time

# 1. SOZLAMALAR
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(','))) if os.getenv("ADMIN_IDS") else []
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
DB_NAME = os.getenv("DB_NAME", "media_bot.db")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# 2. LOGGING
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 3. FLASK VA BOT OBEKTlARI
bot = TeleBot(BOT_TOKEN)
app = Flask(__name__) if USE_WEBHOOK else None

# 4. MA'LUMOTLAR BAZASI
class Database:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db():
        tables = [
            """CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT,
                secret_code TEXT UNIQUE NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                views INTEGER DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_secret_code ON media(secret_code)"
        ]
        
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            for table in tables:
                cursor.execute(table)

    @staticmethod
    def update_user(user: types.User):
        with Database.get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, last_active)
            VALUES (?, ?, ?, ?, ?)
            """, (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

    @staticmethod
    def add_media(file_id: str, file_type: str, file_name: str, secret_code: str):
        with Database.get_connection() as conn:
            conn.execute(
                "INSERT INTO media (file_id, file_type, file_name, secret_code) VALUES (?, ?, ?, ?)",
                (file_id, file_type, file_name, secret_code)
            )

    @staticmethod
    def get_media_by_code(code: str):
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM media WHERE secret_code = ?", (code,))
            return cursor.fetchone()

    @staticmethod
    def increment_views(code: str):
        with Database.get_connection() as conn:
            conn.execute("UPDATE media SET views = views + 1 WHERE secret_code = ?", (code,))

    @staticmethod
    def delete_media(code: str):
        with Database.get_connection() as conn:
            conn.execute("DELETE FROM media WHERE secret_code = ?", (code,))

    @staticmethod
    def get_stats():
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media")
            media_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            return media_count, users_count

    @staticmethod
    def add_admin(user_id: int, added_by: int):
        with Database.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by)
            )

    @staticmethod
    def is_admin_in_db(user_id: int) -> bool:
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None

# 5. YORDAMCHI FUNKTSIYALAR
class Utils:
    _user_requests = defaultdict(list)

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS or Database.is_admin_in_db(user_id)

    @staticmethod
    def is_valid_code(code: str) -> bool:
        return bool(code.strip())

    @staticmethod
    def is_code_available(code: str) -> bool:
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM media WHERE secret_code = ?", (code,))
            return cursor.fetchone() is None

    @staticmethod
    def check_subscription(user_id: int) -> bool:
        try:
            chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
            return chat_member.status in ['member', 'administrator', 'creator']
        except Exception as e:
            logger.error(f"Obunani tekshirishda xato: {e}")
            if "chat not found" in str(e).lower():
                return True
            return False

    @staticmethod
    def is_rate_limited(user_id: int, limit: int = 5, period: int = 60) -> bool:
        now = datetime.now()
        Utils._user_requests[user_id] = [t for t in Utils._user_requests[user_id] if (now - t).seconds < period]
        if len(Utils._user_requests[user_id]) >= limit:
            return True
        Utils._user_requests[user_id].append(now)
        return False

# 6. BOT HANDLERLARI
class BotHandlers:
    BATCH_SIZE = 30  # Telegram API limiti (30 xabar/sekund)
    DELAY = 1        # Har bir batch orasidagi kutish vaqti

    @staticmethod
    def setup_handlers():
        @bot.message_handler(commands=['start'])
        def send_welcome(message: types.Message):
            Database.update_user(message.from_user)
            bot.reply_to(message, f"Assalomu alaykum! Botga xush kelibsiz!\n\nKanalimiz: {CHANNEL_LINK}")

        @bot.message_handler(commands=['admin'])
        def admin_panel(message: types.Message):
            if not Utils.is_admin(message.from_user.id):
                bot.reply_to(message, "⚠️ Sizga ruxsat yo'q!")
                return

            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("📊 Statistika", callback_data="show_stats"),
                types.InlineKeyboardButton("📢 Reklama", callback_data="send_ad")
            )
            markup.row(
                types.InlineKeyboardButton("👤 Admin qo'shish", callback_data="add_admin"),
                types.InlineKeyboardButton("🗑️ Fayl o'chirish", callback_data="delete_file")
            )
            
            bot.send_message(
                message.chat.id,
                "🔐 Admin panelga xush kelibsiz:",
                reply_markup=markup
            )

        @bot.message_handler(func=lambda m: True, content_types=['text'])
        def handle_text(message: types.Message):
            if message.text.startswith('/'):
                bot.reply_to(message, "⚠️ Noma'lum buyruq!")
                return
            
            # Media fayllarni qidirish uchun kod
            media = Database.get_media_by_code(message.text)
            if media:
                Database.increment_views(message.text)
                if media['file_type'] == 'photo':
                    bot.send_photo(message.chat.id, media['file_id'])
                elif media['file_type'] == 'video':
                    bot.send_video(message.chat.id, media['file_id'])
                else:
                    bot.send_document(message.chat.id, media['file_id'])
            else:
                bot.reply_to(message, "❌ Topilmadi! Noto'g'ri kod yoki fayl o'chirilgan.")

        @bot.callback_query_handler(func=lambda call: True)
        def handle_callbacks(call: types.CallbackQuery):
            try:
                if call.data == "show_stats":
                    BotHandlers.handle_show_stats(call)
                elif call.data == "send_ad":
                    BotHandlers.handle_send_ad(call)
                elif call.data == "add_admin":
                    BotHandlers.handle_add_admin(call)
                elif call.data == "delete_file":
                    BotHandlers.handle_delete_file(call)
                    
            except Exception as e:
                logger.error(f"Callback error: {e}")
                bot.answer_callback_query(call.id, "❌ Xatolik yuz berdi!")

        @staticmethod
        def handle_show_stats(call: types.CallbackQuery):
            if not Utils.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
                return
                
            media_count, users_count = Database.get_stats()
            bot.edit_message_text(
                f"📊 Bot statistikasi:\n\n"
                f"• Fayllar soni: {media_count}\n"
                f"• Foydalanuvchilar: {users_count}",
                call.message.chat.id,
                call.message.message_id
            )

        @staticmethod
        def handle_send_ad(call: types.CallbackQuery):
            if not Utils.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
                return
                
            msg = bot.send_message(call.message.chat.id, "📢 Reklama matnini yuboring:")
            bot.register_next_step_handler(msg, BotHandlers.process_ad_text)

        @staticmethod
        def handle_add_admin(call: types.CallbackQuery):
            if not Utils.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
                return
                
            msg = bot.send_message(
                call.message.chat.id,
                "Yangi adminning ID sini yuboring yoki uning xabarini forward qiling:"
            )
            bot.register_next_step_handler(msg, BotHandlers.process_new_admin)

        @staticmethod
        def handle_delete_file(call: types.CallbackQuery):
            if not Utils.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
                return
                
            msg = bot.send_message(call.message.chat.id, "O'chirish uchun fayl kodini yuboring:")
            bot.register_next_step_handler(msg, BotHandlers.process_delete_file)

        @staticmethod
        def process_ad_text(message: types.Message):
            try:
                ad_text = message.text.strip()
                if not ad_text:
                    bot.send_message(message.chat.id, "❌ Reklama matni bo'sh bo'lishi mumkin emas!")
                    return
                    
                users = Database.get_connection().execute("SELECT user_id FROM users").fetchall()
                success, failures = 0, 0
                
                for i, user in enumerate(users):
                    try:
                        if i % BotHandlers.BATCH_SIZE == 0 and i != 0:
                            time.sleep(BotHandlers.DELAY)
                        bot.send_message(user['user_id'], ad_text)
                        success += 1
                    except Exception as e:
                        logger.error(f"Foydalanuvchiga {user['user_id']} reklama yuborishda xato: {e}")
                        failures += 1
                        
                bot.send_message(
                    message.chat.id,
                    f"✅ Reklama yuborish yakunlandi!\n\n"
                    f"✔️ Muvaffaqiyatli: {success}\n"
                    f"❌ Yuborilmadi: {failures}"
                )
                
            except Exception as e:
                logger.error(f"Reklama jarayonida xato: {e}")
                bot.send_message(message.chat.id, "❌ Reklama yuborishda xatolik yuz berdi!")

        @staticmethod
        def process_new_admin(message: types.Message):
            try:
                # Forward qilingan xabardan admin qo'shish
                if message.forward_from:
                    new_admin_id = message.forward_from.id
                else:
                    new_admin_id = int(message.text)
                    
                Database.add_admin(new_admin_id, message.from_user.id)
                bot.send_message(
                    message.chat.id,
                    f"✅ Yangi admin qo'shildi: {new_admin_id}\n"
                    f"Endi u /admin buyrug'i orqali panelga kira oladi."
                )
            except ValueError:
                bot.send_message(message.chat.id, "❌ Noto'g'ri ID formati!")
            except Exception as e:
                logger.error(f"Admin qo'shishda xato: {e}")
                bot.send_message(message.chat.id, "❌ Xatolik yuz berdi!")

        @staticmethod
        def process_delete_file(message: types.Message):
            try:
                code = message.text.strip()
                if not code:
                    bot.send_message(message.chat.id, "❌ Kod kiritilmadi!")
                    return
                    
                Database.delete_media(code)
                bot.send_message(message.chat.id, f"✅ '{code}' kodi bilan fayl o'chirildi!")
            except Exception as e:
                logger.error(f"Fayl o'chirishda xato: {e}")
                bot.send_message(message.chat.id, "❌ Fayl o'chirishda xatolik!")

# 7. WEBHOOK SOZLAMALARI
if USE_WEBHOOK:
    @app.route('/webhook', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_data = request.get_json()
            update = types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return 'ok', 200
        return 'Bad request', 400

# 8. DASTURNI ISHGA TUSHIRISH
if __name__ == "__main__":
    try:
        logger.info("Bot ishga tushmoqda...")
        Database.init_db()
        BotHandlers.setup_handlers()

        if USE_WEBHOOK:
            logger.info("Webhook rejimida ishga tushirilmoqda...")
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            port = int(os.environ.get("PORT", 10000))
            app.run(host='0.0.0.0', port=port)
        else:
            logger.info("Polling rejimida ishga tushirilmoqda...")
            bot.infinity_polling()

    except Exception as e:
        logger.critical(f"Bot ishga tushirishda xato: {e}", exc_info=True)