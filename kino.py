import os
import sqlite3
import random
import logging
from datetime import datetime
from typing import Union

from telebot import TeleBot, types
from telebot.util import quick_markup

from dotenv import load_dotenv
import os

# .env faylni yuklash
load_dotenv()

# O'zgaruvchilarni olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(',')))  # Ro'yxatga aylantirish
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
DB_NAME = os.getenv("DB_NAME")
LOG_FILE = os.getenv("LOG_FILE")


# Loglarni sozlash
logging.basicConfig(
    filename=LOG_FILE,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Botni ishga tushirish
bot = TeleBot(BOT_TOKEN)

# Ma'lumotlar bazasini ishga tushirish
def init_db():
    conn = sqlite3.connect(DB_NAME)
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
    
    conn.commit()
    conn.close()

init_db()

# Foydalanuvchini bazaga qo'shish/yangilash
def update_user(user: types.User):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
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
    
    conn.commit()
    conn.close()

# Admin tekshiruvi
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Kodni tekshirish
def is_valid_code(code: str) -> bool:
    return len(code) == 6 and code.isdigit()

# Obunani tekshirish
def check_subscription(user_id: int) -> bool:
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Obunani tekshirishda xato: {e}")
        return False

# Start komandasi
@bot.message_handler(commands=['start'])
def send_welcome(message: types.Message):
    update_user(message.from_user)
    
    if check_subscription(message.from_user.id):
        text = (
            "👋 Assalomu alaykum! Botdan foydalanish uchun 6 xonali kodni yuboring.\n\n"
            "Agar admin bo'lsangiz, /admin buyrug'i orqali panelga kirishingiz mumkin."
        )
        bot.reply_to(message, text)
    else:
        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)
        btn2 = types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subscription")
        markup.add(btn1, btn2)
        
        text = (
            "👋 Assalomu alaykum! Botdan foydalanish uchun quyidagi kanalga obuna bo'ling.\n\n"
            f"Kanal: {CHANNEL_USERNAME}"
        )
        bot.send_message(message.chat.id, text, reply_markup=markup)

# Obunani tekshirish callback
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def subscription_callback(call: types.CallbackQuery):
    if check_subscription(call.from_user.id):
        bot.edit_message_text(
            "✅ Kanalga obuna bo'ldingiz! Endi media olish uchun kodni yuboring.",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)

# Admin paneli
@bot.message_handler(commands=['admin'])
def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Sizda admin huquqlari yo'q!")
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

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: types.CallbackQuery):
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

# Media yuklash
def process_media_upload(message: types.Message):
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
        bot.reply_to(message, "❌ Faqat video, rasm yoki hujjat yuborishingiz mumkin!")
        return
    
    msg = bot.reply_to(message, "🔢 Iltimos, 6 xonali raqamli kod kiriting:")
    bot.register_next_step_handler(msg, lambda m: save_media_with_code(m, file_id, file_type, file_name))

def save_media_with_code(message: types.Message, file_id: str, file_type: str, file_name: str):
    try:
        code = message.text.strip()
        
        if not is_valid_code(code):
            bot.reply_to(message, "❌ Noto'g'ri format! Iltimos, 6 xonali raqam kiriting.")
            return
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM media WHERE secret_code=?", (code,))
        if cursor.fetchone()[0] > 0:
            bot.reply_to(message, "⚠️ Bu kod allaqachon mavjud. Iltimos, boshqa kod kiriting.")
            return
            
        cursor.execute("""
        INSERT INTO media (file_id, file_type, file_name, secret_code)
        VALUES (?, ?, ?, ?)
        """, (file_id, file_type, file_name, code))
        
        conn.commit()
        
        bot.reply_to(
            message,
            f"✅ Media muvaffaqiyatli yuklandi!\n\n"
            f"📁 Fayl turi: {file_type}\n"
            f"📝 Fayl nomi: {file_name}\n"
            f"🔑 Kodi: <code>{code}</code>\n\n"
            f"Foydalanuvchilar shu kodni yuborish orqali media olishlari mumkin.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Xato yuz berdi: {e}")
        bot.reply_to(message, "❌ Xato yuz berdi. Iltimos, qayta urinib ko'ring.")
    finally:
        conn.close()

# Media kodini qaytarish
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_media_request(message: types.Message):
    if message.text.startswith('/'):
        return
    
    if not check_subscription(message.from_user.id):
        send_welcome(message)
        return
    
    update_user(message.from_user)
    
    code = message.text.strip()
    
    if not is_valid_code(code):
        bot.reply_to(message, "❌ Noto'g'ri kod formati! Iltimos, 6 xonali raqam yuboring.")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        SELECT file_id, file_type, file_name 
        FROM media 
        WHERE secret_code = ?
        """, (code,))
        
        media = cursor.fetchone()
        
        if media:
            file_id, file_type, file_name = media
            
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
                bot.reply_to(message, "❌ Media yuborishda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")
        else:
            bot.reply_to(message, "❌ Kiritgan kodingizga mos media topilmadi.")
            
    except Exception as e:
        logger.error(f"Ma'lumotlar bazasida xato: {e}")
        bot.reply_to(message, "❌ Xato yuz berdi. Iltimos, keyinroq urinib ko'ring.")
    finally:
        conn.close()

# Botni ishga tushirish
if __name__ == "__main__":
    logger.info("Bot ishga tushmoqda...")
    bot.infinity_polling()