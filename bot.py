import os
import openai
import psycopg2
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# 🔐 Ключи и API
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

MAX_HISTORY = 10  # Кол-во последних сообщений
MAX_TOKENS = 1000

# 🗃 Подключение к PostgreSQL
conn = psycopg2.connect(
    host=os.environ["PGHOST"],
    port=os.environ["PGPORT"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
    database=os.environ["PGDATABASE"]
)
conn.autocommit = True

# 📦 Инициализация таблиц
with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            chat_id TEXT PRIMARY KEY,
            messages_sent INTEGER DEFAULT 0,
            symbols_sent INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)

# 💬 Старт из UI
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    keyboard = [
        [
            InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about"),
            InlineKeyboardButton("💎 Купить доступ", url="https://example.com/pay")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    with open("oracle.jpg", "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption="👋 Привет! Я — Оракул. Напиши мне что-нибудь, и я постараюсь помочь.",
            reply_markup=reply_markup
        )

# 💬 Сообщения от пользователя
#async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    chat_id = str(update.effective_chat.id)
#    user_message = update.message.text

    # Проверка: новый ли пользователь
#    with conn.cursor() as cur:
#        cur.execute("SELECT 1 FROM user_stats WHERE chat_id = %s", (chat_id,))
#        is_new_user = cur.fetchone() is None

#    if is_new_user:
#        keyboard = [
#            [
#                InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about"),
#                InlineKeyboardButton("💎 Купить доступ", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
#            ]
#        ]
#        reply_markup = InlineKeyboardMarkup(keyboard)

#        with open("oracle.jpg", "rb") as photo:
#            await context.bot.send_photo(
#                chat_id=chat_id,
#                photo=photo,
#                caption="👋 Привет! Я — Оракул и готов отвечать на вопросы, анализировать сны и не только.",
#                reply_markup=reply_markup
#            )

    # Сохраняем сообщение пользователя
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "user", user_message, datetime.utcnow())
        )

    # Обновляем статистику
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_stats (chat_id, messages_sent, symbols_sent)
            VALUES (%s, 1, %s)
            ON CONFLICT (chat_id)
            DO UPDATE SET
                messages_sent = user_stats.messages_sent + 1,
                symbols_sent = user_stats.symbols_sent + EXCLUDED.symbols_sent,
                updated_at = NOW()
        """, (chat_id, len(user_message)))

    # Загружаем историю
    with conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE chat_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (chat_id, MAX_HISTORY * 2))
        rows = cur.fetchall()
        history = [{"role": role, "content": content} for role, content in reversed(rows)]

    # Показываем "печатает..." и временное сообщение
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("🧠 Оракул размышляет…")

    # GPT-4 запрос
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=history + [{
                "role": "system",
                "content": "Пожалуйста, не превышай 3000 символов в ответе. Отвечай кратко и по существу."
            }],
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Ошибка OpenAI: {e}"

    # Сохраняем ответ
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "assistant", reply, datetime.utcnow())
        )

    # Заменяем временное сообщение на ответ
    await thinking_msg.edit_text(reply)

# 🧠 Обработка нажатия кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "about":
        await query.message.reply_text(
            "🧠 Я могу:\n"
            "• Толковать сны\n"
            "• Отвечать на философские и личные вопросы\n"
            "• Давать советы, предсказания и многое другое"
        )

# 🚀 Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("start", start_command))
    app.run_polling()
