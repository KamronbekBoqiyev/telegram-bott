from telebot import types
from config import CHANNEL_ID

def check_subscription(bot, user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ["member", "administrator", "creator"]
    except:
        return False

def register_handlers(bot):
    @bot.message_handler(commands=["start"])
    def start_handler(msg):
        if not check_subscription(bot, msg.from_user.id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔔 Obuna bo'lish", url="https://t.me/yourchannel"))
            bot.send_message(msg.chat.id, "Botdan foydalanish uchun kanalga obuna bo'ling.", reply_markup=markup)
            return
        bot.send_message(msg.chat.id, "👋 Botga xush kelibsiz! Fayl kodini yuboring yoki fayl yuklang.")
