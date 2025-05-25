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
"Use emoji consistently to illustrate or reinforce key points and symbols. Avoid overusing them. Use them to create lists and emphasize important points."
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
        """, (chat_id, "user", user_message, datetime.now(datetime.UTC)))

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
        log_activity(user, chat_id, "dream_interpreted", reply[:300])

    except Exception as e:
        reply = f"❌ Ошибка OpenAI: {e}"

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO messages (chat_id, role, content, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, "assistant", reply, datetime.utcnow()))
        
    await thinking_msg.edit_text(reply, parse_mode='Markdown')

# --- Обработчик команды /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    log_activity(update.effective_user, str(update.effective_chat.id), "start")

    keyboard = [
        [InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about")],
        [InlineKeyboardButton("🧾 Заполнить анкету", callback_data="start_profile")]
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
        await update.message.reply_text("👋 Привет! Я — Трактователь Снов. Просто опиши свой сон — и я помогу его интерпретировать.", parse_mode='Markdown')


# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_activity(update.effective_user, str(update.effective_chat.id), f"button:{query.data}")

    if query.data == "about":
        await query.message.reply_text(
            "Я могу анализировать сны, отвечать на вопросы, работать с контекстом. Просто опиши свой сон!",
            parse_mode='Markdown'
        )

    elif query.data == "start_profile":
        await query.message.reply_text(
            "🧾 Я хочу лучше понять ваш контекст. Анкета займёт меньше минуты и поможет мне давать более точные трактовки.\n\nНачнём?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да, начать", callback_data="profile_step:gender")],
                [InlineKeyboardButton("Позже", callback_data="profile_step:skip")]
            ])
        )

    elif query.data == "profile_step:gender":
        context.user_data['profile_step'] = "gender"
        await query.message.reply_text(
            "🧾 Вопрос 1 из 3: Какой у вас пол?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Мужской", callback_data="gender:male")],
                [InlineKeyboardButton("Женский", callback_data="gender:female")],
                [InlineKeyboardButton("Другое / Неважно", callback_data="gender:other")]
            ])
        )

    elif query.data == "profile_step:skip":
        await query.message.reply_text("Хорошо! Вы всегда можете вернуться к анкете позже через команду /start.")

    elif query.data.startswith("gender:"):
        gender = query.data.split(":")[1]
        context.user_data['gender'] = gender
        context.user_data['profile_step'] = "age"

        await query.message.reply_text(
            "👤 Вопрос 2 из 3: Укажите возрастную группу",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("До 18", callback_data="age:<18")],
                [InlineKeyboardButton("18–30", callback_data="age:18-30")],
                [InlineKeyboardButton("31–50", callback_data="age:31-50")],
                [InlineKeyboardButton("50+", callback_data="age:50+")]
            ])
        )

    elif query.data.startswith("age:"):
        age = query.data.split(":")[1]
        context.user_data['age_group'] = age
        context.user_data['profile_step'] = "lucid"

        await query.message.reply_text(
            "🌙 Вопрос 3 из 3: Как часто вы испытываете осознанные сны?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Часто", callback_data="lucid:часто")],
                [InlineKeyboardButton("Иногда", callback_data="lucid:иногда")],
                [InlineKeyboardButton("Никогда", callback_data="lucid:никогда")]
            ])
        )

    elif query.data.startswith("lucid:"):
        lucid = query.data.split(":")[1]
        context.user_data['lucid_dreaming'] = lucid
        context.user_data['profile_step'] = None

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profile (chat_id, username, gender, age_group, lucid_dreaming, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (chat_id) DO UPDATE
                SET gender = EXCLUDED.gender,
                    age_group = EXCLUDED.age_group,
                    lucid_dreaming = EXCLUDED.lucid_dreaming,
                    updated_at = now()
            """, (
                str(update.effective_chat.id),
                f"@{update.effective_user.username}" if update.effective_user.username else None,
                context.user_data.get('gender'),
                context.user_data.get('age_group'),
                lucid
            ))
        conn.commit()

        await query.message.reply_text(
            "✅ Спасибо! Профиль сохранён.\nТеперь я смогу учитывать ваш опыт в интерпретации снов."
        )


# --- Инициализация приложения ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
