import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)
from openai import AsyncOpenAI

# --- OpenAI client ---
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- PostgreSQL connection ---
conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    port=os.getenv("PGPORT"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    dbname=os.getenv("PGDATABASE")
)

MAX_TOKENS = 1000
MAX_HISTORY = 10

# --- Default system prompt ---
DEFAULT_SYSTEM_PROMPT = (
"You are a dream analyst trained in the Jungian tradition. Your interpretations rely on archetypes, symbols, and the collective unconscious, based on the works of C.G. Jung, M.-L. von Franz, ARAS, the Jung Institute Zürich, and Chevalier & Gheerbrant's Dictionary of Symbols, including The Book of Symbols."
"Your task is to: Treat each dream as a unique message from the unconscious, Identify key images and archetypes, Interpret them hypothetically, clearly, and respectfully — never predict the future or make categorical claims, Consider characters, setting, and mood. Use simple language, structured paragraphs, and avoid complex or clinical terms."
"If the user shares time/place and requests it, include metaphorical astrological influences (e.g. Moon phase), but never as scientific fact."
"Ask 1–3 clarifying questions if the dream is too brief. If refused, interpret available symbols with care."
"Avoid advice, life coaching, or therapeutic claims. Never use or repeat obscene language — rephrase respectfully instead."
"If the user goes off-topic, gently redirect to dream discussion. Always stay in your role."
"Use formatting according only Telegram sheme. Separate the text into logical paragraphs."
)

# --- Лог активности ---
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
    conn.commit()

# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    log_activity(user, chat_id, "message", user_message)
    log_activity(user, chat_id, "gpt_request", f"model=gpt-4o, temp=0.4, max_tokens={MAX_TOKENS}")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO messages (chat_id, role, content, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, "user", user_message, datetime.utcnow()))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s
        """, (chat_id, MAX_HISTORY * 2))
        rows = cur.fetchall()
        history = [{"role": r, "content": c} for r, c in reversed(rows)]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("👁‍🗨 Изучаю...")

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}] + history,
            temperature=0.4,
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"❌ Ошибка OpenAI: {e}"

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO messages (chat_id, role, content, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, "assistant", reply, datetime.utcnow()))

    await thinking_msg.edit_text(reply)

# --- Обработчик команды /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    log_activity(update.effective_user, str(update.effective_chat.id), "start")

    keyboard = [
        [InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about")],
        [InlineKeyboardButton("💎 Задонатить боту", url="https://example.com/pay")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        with open("oracle.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption="👋 Привет! Я — Трактователь Снов. Просто опиши свой сон — и я помогу его интерпретировать.",
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await update.message.reply_text("👋 Привет! Я — Трактователь Снов. Просто опиши свой сон — и я помогу его интерпретировать.")

# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_activity(update.effective_user, str(update.effective_chat.id), f"button:{query.data}")

    if query.data == "about":
        await query.message.reply_text("Я могу анализировать сны, отвечать на вопросы, работать с контекстом. Просто опиши свой сон!")

# --- Инициализация приложения ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
