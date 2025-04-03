import os
import sqlite3
import logging
from datetime import datetime
from typing import Optional

from telebot import TeleBot, types
from telebot.util import quick_markup
from dotenv import load_dotenv

# Konfiguratsiyani yuklash
load_dotenv()

# Sozlamalarni o'rnatish
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(','))) if os.getenv("ADMIN_IDS") else []
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
DB_NAME = os.getenv("DB_NAME", "media_bot.db")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")

# Loglarni sozlash
logging.basicConfig(
    filename=LOG_FILE,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Botni ishga tushirish
bot = TeleBot(BOT_TOKEN)

# Ma'lumotlar bazasi funktsiyalari
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
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

def update_user(user: types.User):
    with get_db_connection() as conn:
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

# Yordamchi funktsiyalar
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def is_valid_code(code: str) -> bool:
    return len(code) == 6 and code.isdigit()

def check_subscription(user_id: int) -> bool:
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Obunani tekshirishda xato: {e}")
        return False

# Bot komandalari
@bot.message_handler(commands=['start'])
def send_welcome(message: types.Message):
    
    try:
        update_user(message.from_user)
        
        if check_subscription(message.from_user.id):
            text = (
                "👋 Assalomu alaykum! Botdan foydalanish uchun 6 xonali kodni yuboring.\n\n"
                
            )
            bot.send_message(message.chat.id, text)
        else:
            markup = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)
            btn2 = types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subscription")
            markup.add(btn1, btn2)
            
            text = (
                "👋 Assalomu alaykum! Botdan foydalanish uchun quyidagi kanalga obuna bo'ling.\n\n"
                f"Kanal: @{CHANNEL_USERNAME}"
            )
            bot.send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Start command error: {e}")
        bot.send_message(message.chat.id, "⚠️ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def subscription_callback(call: types.CallbackQuery):
    try:
        if check_subscription(call.from_user.id):
            bot.edit_message_text(
                "✅ Kanalga obuna bo'ldingiz! Endi media olish uchun kodni yuboring.",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)
    except Exception as e:
        logger.error(f"Subscription callback error: {e}")

@bot.message_handler(commands=['admin'])
def admin_panel(message: types.Message):
    try:
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "⚠️ Sizda admin huquqlari yo'q!")
            return
        
        markup = quick_markup({
            "📢 Reklama yuborish": {"callback_data": "send_ad"},
            "🎬 Media yuklash": {"callback_data": "upload_media"},
            "📊 Statistika": {"callback_data": "show_stats"}
        }, row_width=2)
        
        bot.send_message(
            message.chat.id,
            "🏠 Admin panelga xush kelibsiz. Quyidagi tugmalardan birini tanlang:",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Admin panel error: {e}")

# Media yuklash va olish
@bot.callback_query_handler(func=lambda call: call.data in ["send_ad", "upload_media", "show_stats"])
def callback_handler(call: types.CallbackQuery):
    try:
        if call.data == "send_ad":
            msg = bot.send_message(
                call.message.chat.id,
                "📝 Reklama matnini yuboring (matn, rasm, video yoki hujjat):"
            )
            bot.register_next_step_handler(msg, process_ad)
        
        elif call.data == "upload_media":
            msg = bot.send_message(
                call.message.chat.id,
                "📤 Yuklamoqchi bo'lgan media faylingizni yuboring (video, rasm yoki hujjat):"
            )
            bot.register_next_step_handler(msg, process_media_upload)
        
        elif call.data == "show_stats":
            show_statistics(call.message)
    except Exception as e:
        logger.error(f"Callback handler error: {e}")

def process_media_upload(message: types.Message):
    try:
        if not is_admin(message.from_user.id):
            return
        
        file_id, file_type, file_name = None, None, None
        
        if message.video:
            file_id = message.video.file_id
            file_type = "video"
            file_name = message.video.file_name or "video.mp4"
        elif message.document:
            file_id = message.document.file_id
            file_type = "document"
            file_name = message.document.file_name or "file.bin"
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
            file_name = "photo.jpg"
        else:
            bot.send_message(message.chat.id, "❌ Faqat video, rasm yoki hujjat yuborishingiz mumkin!")
            return
        
        msg = bot.send_message(message.chat.id, "🔢 Iltimos, 6 xonali raqamli kod kiriting:")
        bot.register_next_step_handler(msg, lambda m: save_media_with_code(m, file_id, file_type, file_name))
    except Exception as e:
        logger.error(f"Media upload error: {e}")

def save_media_with_code(message: types.Message, file_id: str, file_type: str, file_name: str):
    try:
        if not is_admin(message.from_user.id):
            return
            
        code = message.text.strip()
        
        if not is_valid_code(code):
            bot.send_message(message.chat.id, "❌ Noto'g'ri format! Iltimos, 6 xonali raqam kiriting.")
            return
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media WHERE secret_code=?", (code,))
            if cursor.fetchone()[0] > 0:
                bot.send_message(message.chat.id, "⚠️ Bu kod allaqachon mavjud. Iltimos, boshqa kod kiriting.")
                return
                
            cursor.execute("""
            INSERT INTO media (file_id, file_type, file_name, secret_code)
            VALUES (?, ?, ?, ?)
            """, (file_id, file_type, file_name, code))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                f"✅ Media muvaffaqiyatli yuklandi!\n\n"
                f"📁 Fayl turi: {file_type}\n"
                f"📝 Fayl nomi: {file_name}\n"
                f"🔑 Kodi: <code>{code}</code>\n\n"
                f"Foydalanuvchilar shu kodni yuborish orqali media olishlari mumkin.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Save media error: {e}")
        bot.send_message(message.chat.id, "❌ Xato yuz berdi. Iltimos, qayta urinib ko'ring.")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_media_request(message: types.Message):
    try:
        if message.text.startswith('/'):
            return
        
        update_user(message.from_user)
        
        if not check_subscription(message.from_user.id):
            send_welcome(message)
            return
        
        code = message.text.strip()
        
        if not is_valid_code(code):
            bot.send_message(message.chat.id, "❌ Noto'g'ri kod formati! Iltimos, 6 xonali raqam yuboring.")
            return
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT file_id, file_type, file_name 
            FROM media 
            WHERE secret_code = ?
            """, (code,))
            
            media = cursor.fetchone()
            
            if media:
                file_id, file_type, file_name = media['file_id'], media['file_type'], media['file_name']
                
                cursor.execute("""
                UPDATE media 
                SET views = views + 1 
                WHERE secret_code = ?
                """, (code,))
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

def show_statistics(message: types.Message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Umumiy statistika
            cursor.execute("SELECT COUNT(*) FROM media")
            media_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(views) FROM media")
            total_views = cursor.fetchone()[0] or 0
            
            # Eng ko'p ko'rilgan media
            cursor.execute("""
            SELECT file_name, secret_code, views 
            FROM media 
            ORDER BY views DESC 
            LIMIT 5
            """)
            top_media = cursor.fetchall()
            
            stats_text = (
                "📊 Bot statistikasi:\n\n"
                f"📁 Jami media fayllar: {media_count}\n"
                f"👥 Foydalanuvchilar soni: {users_count}\n"
                f"👀 Jami ko'rishlar: {total_views}\n\n"
                "🏆 Eng ko'p ko'rilgan media:\n"
            )
            
            for i, media in enumerate(top_media, 1):
                stats_text += f"{i}. {media['file_name']} (kod: {media['secret_code']}) - {media['views']} ko'rish\n"
            
            bot.send_message(message.chat.id, stats_text)
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        bot.send_message(message.chat.id, "❌ Statistikani yuklashda xatolik yuz berdi.")



        

def process_ad(message: types.Message):
    try:
        if not is_admin(message.from_user.id):
            return
            
        # Foydalanuvchilar ro'yxatini olish
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()
            
        # Reklamani yuborish
        success = 0
        failures = 0
        
        for user in users:
            try:
                if message.content_type == 'text':
                    bot.send_message(user['user_id'], message.text)
                elif message.content_type == 'photo':
                    bot.send_photo(user['user_id'], message.photo[-1].file_id, caption=message.caption)
                elif message.content_type == 'video':
                    bot.send_video(user['user_id'], message.video.file_id, caption=message.caption)
                elif message.content_type == 'document':
                    bot.send_document(user['user_id'], message.document.file_id, caption=message.caption)
                success += 1
            except Exception as e:
                logger.error(f"Reklamani {user['user_id']} ga yuborishda xato: {e}")
                failures += 1
        
        bot.send_message(
            message.chat.id,
            f"✅ Reklama yuborildi!\n\n"
            f"✔️ Muvaffaqiyatli: {success}\n"
            f"❌ Muvaffaqiyatsiz: {failures}"
        )
    except Exception as e:
        logger.error(f"Ad process error: {e}")
        bot.send_message(message.chat.id, "❌ Reklama yuborishda xatolik yuz berdi.")




# Dasturni ishga tushirish
if __name__ == "__main__":
    logger.info("Bot ishga tushmoqda...")
    try:
        init_db()
        bot.infinity_polling()
    except Exception as e:
        logger.critical(f"Bot ishga tushirishda xato: {e}")