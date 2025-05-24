# --- Импорт ---
import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)
from openai import AsyncOpenAI

# --- подключение OpenAI ---
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- подключение PostgreSQL ---
conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    port=os.getenv("PGPORT"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    dbname=os.getenv("PGDATABASE")
)

MAX_TOKENS = 1000
MAX_HISTORY = 10


# --- лог активностей ---
def log_activity(user, chat_id, action, content=""):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_activity_log (user_id, username, chat_id, action, content)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            user.id,
            f"@{user.username}" if user.username else None,
            chat_id,
            action,
            content[:1000]
        ))


# --- основной обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    user = update.effective_user

    log_activity(user, chat_id, "message", user_message)

    # сохраняем сообщение
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "user", user_message, datetime.utcnow())
        )

    # достаём историю
    with conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE chat_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (chat_id, MAX_HISTORY * 2))
        rows = cur.fetchall()
        history = [{"role": role, "content": content} for role, content in reversed(rows)]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("🧠 Оракул размышляет…")

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=history + [{
                "role": "system",
                "content": "Пожалуйста, не превышай 3000 символов. Учитывай возраст, если он указан."
            }],
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content

    except Exception as e:
        reply = f"Ошибка OpenAI: {e}"

    # сохраняем ответ
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "assistant", reply, datetime.utcnow())
        )

    await thinking_msg.edit_text(reply)


# --- команда /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    log_activity(user, str(chat_id), "start")

    keyboard = [
        [InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about")],
        [InlineKeyboardButton("💎 Купить доступ", url="https://example.com/pay")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    with open("oracle.jpg", "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption="👋 Привет! Я — Оракул. Напиши свой вопрос.",
            reply_markup=reply_markup
        )


# --- кнопки ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_activity(query.from_user, str(query.message.chat.id), f"button:{query.data}")

    if query.data == "about":
        await query.message.reply_text("Я могу анализировать сны, отвечать на вопросы, работать с контекстом. Просто задай вопрос!")

# --- запуск бота ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
