import os
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict
from collections import defaultdict
import random
import string
from telebot import TeleBot, types
from telebot.util import quick_markup
from dotenv import load_dotenv

# 1. SOZLAMALAR VA BOSHLANG'ICH KONFIGURATSIYA
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(','))) if os.getenv("ADMIN_IDS") else []
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
DB_NAME = os.getenv("DB_NAME", "media_bot.db")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = TeleBot(BOT_TOKEN)

# 2. MA'LUMOTLAR BAZASI FUNKTSIYALARI
class Database:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def init_db():
        with Database.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT,
                secret_code TEXT UNIQUE NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                views INTEGER DEFAULT 0
            )
            """)
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_secret_code ON media(secret_code)")

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

# 3. YORDAMCHI FUNKTSIYALAR
class Utils:
    _user_requests = defaultdict(list)

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS

    @staticmethod
    def is_valid_code(code: str) -> bool:
        """Endi kod har qanday uzunlikda bo'lishi mumkin, lekin bo'sh bo'lmasligi kerak"""
        return bool(code.strip())

    @staticmethod
    def is_code_available(code: str) -> bool:
        """Kod bazada mavjudligini tekshiradi"""
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
                return True  # Kanal topilmasa obuna talab qilinmaydi
            return False

    @staticmethod
    def is_rate_limited(user_id: int, limit: int = 5, period: int = 60) -> bool:
        now = datetime.now()
        Utils._user_requests[user_id] = [t for t in Utils._user_requests[user_id] if (now - t).seconds < period]
        if len(Utils._user_requests[user_id]) >= limit:
            return True
        Utils._user_requests[user_id].append(now)
        return False

# 4. BOT HANDLERLARI
class BotHandlers:
    @staticmethod
    def setup_handlers():
        @bot.message_handler(commands=['start'])
        def send_welcome(message: types.Message):
            try:
                Database.update_user(message.from_user)

                if Utils.check_subscription(message.from_user.id):
                    text = "👋 Assalomu alaykum! Botdan foydalanish uchun kodni yuboring."
                    bot.send_message(message.chat.id, text)
                else:
                    markup = types.InlineKeyboardMarkup()
                    btn1 = types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)
                    btn2 = types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subscription")
                    markup.add(btn1, btn2)

                    text = f"👋 Assalomu alaykum! Botdan foydalanish uchun quyidagi kanalga obuna bo'ling.\n\nKanal: @{CHANNEL_USERNAME}"
                    bot.send_message(message.chat.id, text, reply_markup=markup)
            except Exception as e:
                logger.error(f"Start command error: {e}")
                bot.send_message(message.chat.id, "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")

        @bot.message_handler(commands=['admin'])
        def admin_panel(message: types.Message):
            if not Utils.is_admin(message.from_user.id):
                bot.send_message(message.chat.id, "⚠️ Sizda admin huquqlari yo'q!")
                return

            markup = quick_markup({
                "📢 Reklama yuborish": {"callback_data": "send_ad"},
                "🎬 Media yuklash": {"callback_data": "upload_media"},
                "📊 Statistika": {"callback_data": "show_stats"}
            }, row_width=2)

            bot.send_message(message.chat.id, "🏠 Admin panelga xush kelibsiz. Quyidagi tugmalardan birini tanlang:", reply_markup=markup)

        @bot.message_handler(func=lambda m: True, content_types=['text'])
        def handle_media_request(message: types.Message):
            try:
                if message.text.startswith('/'):
                    return

                if Utils.is_rate_limited(message.from_user.id):
                    bot.send_message(message.chat.id, "❌ Juda ko'p so'rovlar! Iltimos, biroz kutib turing.")
                    return

                Database.update_user(message.from_user)

                if not Utils.check_subscription(message.from_user.id):
                    send_welcome(message)
                    return

                code = message.text.strip()

                if not Utils.is_valid_code(code):
                    bot.send_message(message.chat.id, "❌ Noto'g'ri kod formati! Kod bo'sh bo'lmasligi kerak.")
                    return

                with Database.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT file_id, file_type, file_name FROM media WHERE secret_code = ?", (code,))
                    media = cursor.fetchone()

                    if media:
                        file_id, file_type, file_name = media['file_id'], media['file_type'], media['file_name']
                        cursor.execute("UPDATE media SET views = views + 1 WHERE secret_code = ?", (code,))
                        conn.commit()

                        try:
                            if file_type == "video":
                                bot.send_video(message.chat.id, file_id, caption=f"🎥 Kod: {code}")
                            elif file_type == "document":
                                bot.send_document(message.chat.id, file_id, caption=f"📄 Kod: {code}")
                            elif file_type == "photo":
                                bot.send_photo(message.chat.id, file_id, caption=f"🖼 Kod: {code}")
                        except Exception as e:
                            logger.error(f"Media yuborishda xato: {e}")
                            bot.send_message(message.chat.id, "❌ Media yuborishda xatolik yuz berdi.")
                    else:
                        bot.send_message(message.chat.id, "❌ Kiritgan kodingizga mos media topilmadi.")
            except Exception as e:
                logger.error(f"Media request error: {e}")
                bot.send_message(message.chat.id, "❌ Xato yuz berdi. Iltimos, keyinroq urinib ko'ring.")

        @bot.callback_query_handler(func=lambda call: call.data == 'upload_media')
        def handle_upload_media(call: types.CallbackQuery):
            if not Utils.is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
                return
            
            msg = bot.send_message(call.message.chat.id, "📤 Yuklamoqchi bo'lgan media faylingizni yuboring (video, rasm yoki dokument)")
            bot.register_next_step_handler(msg, BotHandlers.process_media_file)

    @staticmethod
    def process_media_file(message: types.Message):
        try:
            if message.content_type not in ['photo', 'video', 'document']:
                bot.send_message(message.chat.id, "❌ Noto'g'ri format! Faqat video, rasm yoki dokument yuboring.")
                return
                
            file_id = None
            file_type = message.content_type
            file_name = None
            
            if file_type == 'photo':
                file_id = message.photo[-1].file_id
                file_name = "photo.jpg"
            elif file_type == 'video':
                file_id = message.video.file_id
                file_name = message.video.file_name or "video.mp4"
            elif file_type == 'document':
                file_id = message.document.file_id
                file_name = message.document.file_name
                
            # Admin dan kodni so'rash
            msg = bot.send_message(message.chat.id, "🔢 Media uchun kod kiriting (har qanday uzunlikdagi raqam yoki harflar):")
            bot.register_next_step_handler(msg, lambda m: BotHandlers.save_media_with_code(m, file_id, file_type, file_name))
            
        except Exception as e:
            logger.error(f"Media saqlashda xato: {e}")
            bot.send_message(message.chat.id, "❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    @staticmethod
    def save_media_with_code(message: types.Message, file_id: str, file_type: str, file_name: str):
        try:
            secret_code = message.text.strip()
            
            if not Utils.is_valid_code(secret_code):
                bot.send_message(message.chat.id, "❌ Noto'g'ri kod formati! Kod bo'sh bo'lmasligi kerak.")
                return
                
            if not Utils.is_code_available(secret_code):
                bot.send_message(message.chat.id, f"❌ Bu kod allaqachon band: {secret_code}")
                return
                
            # Bazaga saqlash
            with Database.get_connection() as conn:
                conn.execute(
                    "INSERT INTO media (file_id, file_type, file_name, secret_code) VALUES (?, ?, ?, ?)",
                    (file_id, file_type, file_name, secret_code)
                )
                
            bot.send_message(
                message.chat.id,
                f"✅ Media saqlandi!\n\n🔐 Kirish kodi: <code>{secret_code}</code>",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Media saqlashda xato: {e}")
            bot.send_message(message.chat.id, "❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

# 5. DASTURNI ISHGA TUSHIRISH
if __name__ == "__main__":
    try:
        logger.info("Bot ishga tushmoqda...")
        logger.info(f"Adminlar ro'yxati: {ADMIN_IDS}")
        logger.info(f"Kanal username: @{CHANNEL_USERNAME}")

        Database.init_db()
        BotHandlers.setup_handlers()

        bot.infinity_polling()
    except Exception as e:
        logger.critical(f"Bot ishga tushirishda xato: {e}", exc_info=True)