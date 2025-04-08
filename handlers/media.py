import random, string
from database import save_file, get_file, increment_views
from telebot import types

def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def register_handlers(bot):
    @bot.message_handler(content_types=["document", "video", "audio"])
    def handle_media(msg):
        file_type = msg.content_type
        file_id = getattr(msg, file_type).file_id
        caption = msg.caption or ""
        code = generate_code()
        format = "mp4" if file_type == "video" else "mp3"
        save_file(code, msg.from_user.id, file_id, file_type, format, caption)

        text = f"✅ Faylingiz saqlandi!\n🆔 Kod: `{code}`\n📎 Format: {format}"
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")

    @bot.message_handler(func=lambda m: len(m.text) == 6)
    def handle_code(msg):
        record = get_file(msg.text.upper())
        if not record:
            bot.send_message(msg.chat.id, "❌ Fayl topilmadi yoki o‘chirilgan.")
            return
        increment_views(msg.text.upper())
        _, user_id, file_id, file_type, format, caption, views, _ = record

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ O‘chirish", callback_data=f"delete:{msg.text}"))

        bot.send_message(
            msg.chat.id,
            f"📥 Fayl:\n🆔 Kod: `{msg.text}`\n👁 Ko‘rishlar: {views + 1}\n📎 Format: {format}",
            parse_mode="Markdown"
        )

        getattr(bot, f"send_{file_type}")(msg.chat.id, file_id, caption=caption, reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("delete:"))
    def delete_file(call):
        code = call.data.split(":")[1]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "🗑 Fayl o‘chirildi.")
