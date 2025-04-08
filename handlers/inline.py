def register_handlers(bot):
    @bot.inline_handler(func=lambda query: len(query.query) == 6)
    def inline_code_query(inline_query):
        from database import get_file
        record = get_file(inline_query.query.upper())
        if not record:
            return

        _, _, file_id, file_type, _, caption, views, _ = record
        from telebot.types import InlineQueryResultArticle, InputTextMessageContent

        results = [
            InlineQueryResultArticle(
                id=inline_query.id,
                title="📥 Faylni olish",
                input_message_content=InputTextMessageContent(f"🆔 Kod: {inline_query.query}\n👁 Ko‘rishlar: {views}"),
                description=caption,
            )
        ]
        bot.answer_inline_query(inline_query.id, results)
