from config import ADMIN_IDS, DB_NAME
from telebot import types
import sqlite3
import logging

logger = logging.getLogger(__name__)

def register_admin_handlers(bot):
    
    # 1. Yordamchi funksiyalar
    def get_db_connection():
        """Bazaga yangi ulanish ochish"""
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    def is_admin(user_id: int) -> bool:
        """Foydalanuvchi admin ekanligini tekshirish"""
        return user_id in ADMIN_IDS

    # 2. Admin komandalari
    @bot.message_handler(commands=["admin"])
    @admin_required
    def admin_panel(message: types.Message):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media")
            total_files = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stats"),
            types.InlineKeyboardButton("🗑 Fayl o'chirish", callback_data="admin_delete")
        )
        
        bot.send_message(
            message.chat.id,
            f"👑 Admin panel\n\n"
            f"📂 Fayllar: {total_files}\n"
            f"👥 Foydalanuvchilar: {total_users}",
            reply_markup=markup
        )

    @bot.message_handler(commands=['del', 'delete'])
    @admin_required
    def handle_delete(message: types.Message):
        if len(message.text.split()) < 2:
            bot.reply_to(message, "ℹ️ Format: /delete <code>")
            return
            
        code = message.text.split()[1].strip()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media WHERE secret_code=?", (code,))
            conn.commit()
            
            if cursor.rowcount > 0:
                bot.reply_to(message, f"✅ '{code}' o'chirildi")
                logger.info(f"Admin {message.from_user.id} deleted file: {code}")
            else:
                bot.reply_to(message, f"❌ '{code}' topilmadi")

    @bot.message_handler(commands=['list'])
    @admin_required
    def list_files(message: types.Message):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT secret_code, file_name, upload_time 
                FROM media 
                ORDER BY upload_time DESC 
                LIMIT 20
            """)
            files = cursor.fetchall()
            
        if not files:
            bot.reply_to(message, "📭 Fayllar topilmadi")
            return
            
        response = "📂 So'ngi 20 fayl:\n\n"
        for file in files:
            response += (
                f"▫️ {file['file_name']}\n"
                f"🔐 Kodi: {file['secret_code']}\n"
                f"🕒 {file['upload_time']}\n\n"
            )
            
        bot.reply_to(message, response)

    # 3. Callback handlerlar
    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def admin_callback_handler(call: types.CallbackQuery):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⚠️ Ruxsat yo'q!", show_alert=True)
            return
            
        if call.data == 'admin_stats':
            # Statistika logikasi
            pass
        elif call.data == 'admin_delete':
            # O'chirish uchun kod so'rash
            msg = bot.send_message(call.message.chat.id, "🗑 O'chirish uchun kod yuboring:")
            bot.register_next_step_handler(msg, handle_delete)