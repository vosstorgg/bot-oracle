import os
import psycopg2
from datetime import datetime, timezone
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
    "You are a dream analyst trained in the Jungian tradition. Your interpretations rely on archetypes, symbols, and the collective unconscious, "
    "based on the works of C.G. Jung, M.-L. von Franz, ARAS, the Jung Institute Zürich, and Chevalier & Gheerbrant's Dictionary of Symbols, including The Book of Symbols. "
    "Treat each dream as a unique message from the unconscious. Identify key images and archetypes. Interpret them hypothetically, clearly, and respectfully — never predict the future or make categorical claims. "
    "Always consider the dream's characters, setting, atmosphere, and structure. Use simple language, avoid clinical or overly technical terms, and structure your reply into logical paragraphs. "
    "Use only Telegram Markdown formatting (e.g. *bold*, _italic_, `code`) and emojis to illustrate symbols (e.g. 🌑, 👁, 🪞). Do not use HTML. "
    "If the dream is too brief, ask up to 3 clarifying questions. If refused, proceed carefully with the available content. "
    "If the user asks non-dream-related questions, gently redirect to dream interpretation. Never offer life advice, coaching, or therapeutic guidance. "
    "Replace any inappropriate or obscene language with respectful synonyms and continue. Always remain in your role as a symbolic interpreter."
    "\n\n# User context\n"
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

    # Сохраняем сообщение пользователя
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO messages (chat_id, role, content, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, "user", user_message, datetime.now(timezone.utc)))

    # Загружаем историю
    with conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s
        """, (chat_id, MAX_HISTORY * 2))
        rows = cur.fetchall()
        history = [{"role": r, "content": c} for r, c in reversed(rows)]

    # Получаем анкету пользователя
    with conn.cursor() as cur:
        cur.execute("""
            SELECT gender, age_group, lucid_dreaming FROM user_profile
            WHERE chat_id = %s
        """, (chat_id,))
        profile = cur.fetchone()

    profile_info = ""
    if profile:
        gender, age_group, lucid = profile
        if gender:
            profile_info += f"User gender: {gender}. "
        if age_group:
            profile_info += f"User age group: {age_group}. "
        if lucid:
            profile_info += f"Lucid dream experience: {lucid}. "

    # Собираем персонализированный prompt
    personalized_prompt = DEFAULT_SYSTEM_PROMPT
    if profile_info:
        personalized_prompt += f"\n\n# User context\n{profile_info.strip()}"

    # Отправка "размышляет"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("👁‍🗨 Изучаю...")

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": personalized_prompt}] + history,
            temperature=0.4,
            max_tokens=MAX_TOKENS
        )
        reply = response.choices[0].message.content
        log_activity(user, chat_id, "dream_interpreted", reply[:300])
    except Exception as e:
        reply = f"❌ Ошибка OpenAI: {e}"

    # Сохраняем ответ
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO messages (chat_id, role, content, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (chat_id, "assistant", reply, datetime.now(timezone.utc)))

    await thinking_msg.edit_text(reply, parse_mode='Markdown')

# --- Обработчик команды /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    log_activity(update.effective_user, str(update.effective_chat.id), "start")

    keyboard = [
        [InlineKeyboardButton("🧾 Рассказать о себе", callback_data="start_profile")],
        [InlineKeyboardButton("🧠 Что ты умеешь?", callback_data="about")],
        [InlineKeyboardButton("💎 Задонатить боту", callback_data="donate")],
        [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        with open("intro.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption="👋 Привет! Я — Толкователь Снов. Пожалуйста, расскажи о себе, нажав кнопку ниже — это позволит мне лучше понимать для кого я трактую сны. Или можешь просто описать свой сон и я расскажу тебе его скрытые смыслы",
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await update.message.reply_text(
            "👋 Привет! Я — Толкователь Снов. Пожалуйста, расскажи о себе, нажав кнопку ниже — это позволит мне лучше понимать для кого я трактую сны. Или можешь просто описать свой сон и я расскажу тебе его скрытые смыслы",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_activity(update.effective_user, str(update.effective_chat.id), f"button:{query.data}")

    if query.data == "about":
    with open("about.jpg", "rb") as photo:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo,
            caption="Я Толкователь снов, и я расскажу о себе",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
            ])
        )
    
    elif query.data == "donate":
    with open("donate.jpg", "rb") as photo:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo,
            caption="💸 Спасибо за желание поддержать проект!\n\nВыберите сумму поддержки:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Чашка кофе (200 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=200")],
                [InlineKeyboardButton("Кофе с тортиком (500 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=500")],
                [InlineKeyboardButton("Оплата сервера (1000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=1000")],
                [InlineKeyboardButton("Большая благодарность (2000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=2000")],
                [InlineKeyboardButton("Огромная благодарность (5000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=5000")]
            ])
        )

    elif query.data == "start_profile":
    with open("quiz.jpg", "rb") as photo:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo,
            caption="🧾 Я хочу лучше вас понимать. Анкета займёт меньше минуты и поможет мне давать более точные трактовки.\n\nНачнём?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да, начать", callback_data="profile_step:gender")],
                [InlineKeyboardButton("Позже", callback_data="profile_step:skip")]
            ])
        )

    elif query.data == "profile_step:gender":
        context.user_data['profile_step'] = "gender"
        await query.message.reply_text(
            "🧾 Вопрос 1 из 3:\n\nУкажите ваш пол",
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
            "👤 Вопрос 2 из 3:\n\nУкажите ваш возраст",
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
            "🌙 Вопрос 3 из 3:\n\nКак часто вы испытываете осознанные сны?",
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
            "✅ Спасибо! Я записал для себя ответы.\nТеперь я смогу учитывать ваш опыт в интерпретации снов.",
            reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
        ])
    )
        
    elif query.data == "start_first_dream":
        await query.message.reply_text(
        "✨ Расскажи особенно подробно — кто в твоём сне, где ты был, что чувствовал. "
        "Чем больше деталей, тем точнее получится интерпретация. Я весь внимание..."
    )


# --- Инициализация приложения ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
