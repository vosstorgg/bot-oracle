import os
import psycopg2 # type: ignore
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton # type: ignore
from telegram.ext import ( # type: ignore
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)
from openai import AsyncOpenAI # type: ignore

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
    "Ты — Трактователь снов, искусственный интеллект, который анализирует исключительно сны. "
    "Ты применяешь юнгианский подход: работаешь с архетипами, символами, коллективным бессознательным. "
    "Ты не психотерапевт, не лайф-коуч и не собеседник. Ты трактуешь только образы сна. "
    "Если пользователь пишет сообщение, которое не похоже на сон, ты вежливо отвечаешь: 'Я могу интерпретировать только сны...' "
    "Сны могут быть бессмысленными, бытовыми, страшными, абсурдными. Ты говоришь просто, избегаешь медицинской терминологии и сленга." 
    "Ты не осуждаешь и не поддерживаешь пользователя, а стараешься быть беспристрастным" 
    "Ты можешь доуточнять детали сна и помогать их трактовать в формате диалога, не переписывая трактовку полностью"
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

# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    user = update.effective_user

    # Классификация
    guard_prompt = [
        {"role": "system", "content": "Ты — классификатор. Ответь строго 'сон' или 'не сон'."},
        {"role": "user", "content": user_message}
    ]

    guard_response = await openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=guard_prompt,
        max_tokens=1,
        temperature=0
    )

    guard_result = guard_response.choices[0].message.content.strip().lower()
    if guard_result != "сон":
        await update.message.reply_text("🛌 Я могу интерпретировать только сны. Пожалуйста, опишите сновидение.")
        log_activity(user, chat_id, "rejected_non_dream", user_message)
        return

    log_activity(user, chat_id, "message", user_message)

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
    thinking_msg = await update.message.reply_text("🧠 Оракул размышляет…")

    log_activity(user, chat_id, "gpt_request", f"model=gpt-4o, temp=0.4, max_tokens={MAX_TOKENS}")

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
    log_activity(user, str(chat_id), "start")

    keyboard = [
        [InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about")],
        [InlineKeyboardButton("💎 Купить доступ", url="https://example.com/pay")]
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
    log_activity(query.from_user, str(query.message.chat.id), f"button:{query.data}")

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
