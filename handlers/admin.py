from config import ADMIN_IDS
# handlers/admin.py
import sqlite3
from telebot import types
from config import ADMIN_IDS, DB_NAME


from telebot import types
from telebot.util import quick_markup
from config import ADMIN_IDS, DB_NAME
import sqlite3
import logging

def register_admin_handlers(bot):

    
    # Ma'lumotlar bazasiga ulanish
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    @bot.message_handler(commands=["admin"])
    def admin_panel(msg: types.Message):
        if msg.from_user.id not in ADMIN_IDS:
            return
            
        cur.execute("SELECT COUNT(*) FROM media")
        total = cur.fetchone()[0]
        bot.send_message(msg.chat.id, f"📊 Jami yuklangan fayllar: {total}")

    @bot.message_handler(commands=['del'])
    def handle_delete(message: types.Message):
        if message.from_user.id not in ADMIN_IDS:
            bot.reply_to(message, "⚠️ Ruxsat yo'q!")
            return
            
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "ℹ️ Iltimos, kod kiriting: /delete 123456")
            return
            
        # Faylni o'chirish funksiyasi
        cur.execute("DELETE FROM media WHERE secret_code=?", (args[1],))
        conn.commit()
        
        if cur.rowcount > 0:
            bot.reply_to(message, f"✅ {args[1]} kodli fayl o'chirildi")
        else:
            bot.reply_to(message, f"❌ {args[1]} kodli fayl topilmadi")

    # Fayllar ro'yxatini ko'rsatish
    @bot.message_handler(commands=['list'])
    def list_files(message: types.Message):
        if message.from_user.id not in ADMIN_IDS:
            return
            
        cur.execute("SELECT secret_code, file_name FROM media ORDER BY upload_time DESC LIMIT 20")
        files = cur.fetchall()
        
        if not files:
            bot.reply_to(message, "📭 Hozircha fayllar mavjud emas")
            return
            
        response = "📂 Yuklangan fayllar:\n\n"
        for file in files:
            response += f"🔹 {file[1]} (kod: {file[0]})\n"
            
        bot.reply_to(message, response)

        