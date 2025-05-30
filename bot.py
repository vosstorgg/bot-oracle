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

MAX_TOKENS = 1400
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
    thinking_msg = await update.message.reply_text("〰️ Размышляю...")

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
        reply = f"❌ Ошибка, повторите ещё раз: {e}"

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
        [InlineKeyboardButton("🧾 Познакомимся?", callback_data="start_profile")],
        [InlineKeyboardButton("🔮 Что я умею", callback_data="about")],
        [InlineKeyboardButton("💬 Поделиться впечатлениями", url="https://t.me/dream_sense_chat")],
        [InlineKeyboardButton("💎 Донат на развитие", callback_data="donate")],
        [InlineKeyboardButton("🌙 Разобрать мой сон", callback_data="start_first_dream")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        with open("intro.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption="💤 Сны – это не просто странные истории. Это язык, на котором бессознательное разговаривает с тобой. Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. Но за каждым сном – что-то очень личное, что-то только про тебя.\n\nЧто происходит внутри? Что ты чувствуешь, но не замечаешь? К чему ты готов(а), хотя ещё не знаешь этого?\n\nРасскажи, что тебе приснилось. А я постараюсь перевести это на понятный язык.",
                
                reply_markup=reply_markup
            )
            
    except FileNotFoundError:
        await update.message.reply_text(
            "💤 Сны – это не просто странные истории. Это язык, на котором бессознательное разговаривает с тобой. Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. Но за каждым сном – что-то очень личное, что-то только про тебя.\n\nЧто происходит внутри? Что ты чувствуешь, но не замечаешь? К чему ты готов(а), хотя ещё не знаешь этого?\n\nРасскажи, что тебе приснилось. А я постараюсь перевести это на понятный язык.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log_activity(update.effective_user, str(update.effective_chat.id), f"button:{query.data}")

    if query.data == "about":
        with open("about.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption="Я – чат-бот, который помогает тебе понять свои сны. Моя основа — психологический анализ, прежде всего методика Карла Юнга. Мне можно рассказать любой сон – даже самый короткий, запутанный или необычный – и узнать, что хочет подсказать тебе твоё подсознание.\n\nЯ бережно помогаю, не осуждаю и не даю готовых ответов, не навязываю смыслов. Я просто рядом — чтобы помочь тебе чуть ближе подойти к себе, к своему внутреннему знанию, к тому, что обычно остаётся в тени.\n\nВот что я умею:\n🌙 Толкую сны с опорой на образы, архетипы и символы\n💬 Учитываю стиль общения, в котором тебе комфортно – кратко или развернуто, серьёзно или с лёгкостью\n🦄 Могу обсудить с тобой символику сна более подробно и ответить на вопросы\n🪐По запросу – учитываю дату и место сна, чтобы добавить астрологический контекст, исходя из положения планет в это время\n🕊️Говорю с тобой бережно и помогаю взглянуть на сон, как на путь к пониманию себя\n\nЕсли хочешь – просто расскажи свой сон. Я здесь, чтобы слушать и истолковывать",
                
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
                ])
            )
    
    elif query.data == "donate":
        with open("donate.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption="💸 Спасибо за желание поддержать проект! Мне ещё так многому надо научиться!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Перейти к оплате", url="https://pay.cloudtips.ru/p/4f1dd4bf")]
                    #[InlineKeyboardButton("Кофе с тортиком (500 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=500")],
                    #[InlineKeyboardButton("Оплата сервера (1000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=1000")],
                    #[InlineKeyboardButton("Большая благодарность (2000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=2000")],
                    #[InlineKeyboardButton("Огромная благодарность (5000 ₽)", url="https://yoomoney.ru/to/XXXXXXXX?amount=5000")]
                ])
            )

    elif query.data == "start_profile":
        with open("quiz.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo,
                caption="🧾 Всего 3 коротких вопроса, которые помогут мне лучше трактовать твои сны.\n\nНачнём?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Начинаем", callback_data="profile_step:gender")],
                    [InlineKeyboardButton("Давай не сейчас", callback_data="profile_step:skip")]
                ])
            )

    elif query.data == "profile_step:gender":
        context.user_data['profile_step'] = "gender"
        await query.message.reply_text(
            "Символика снов у женщин и мужчин немного отличается. Ты:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Женщина", callback_data="gender:female")],
                [InlineKeyboardButton("Мужчина", callback_data="gender:male")],
                [InlineKeyboardButton("Не скажу", callback_data="gender:other")]
            ])
        )

    elif query.data == "profile_step:skip":
        await query.message.reply_text("Хорошо! Вы всегда можете вернуться к анкете позже через команду /start.")

    elif query.data.startswith("gender:"):
        gender = query.data.split(":")[1]
        context.user_data['gender'] = gender
        context.user_data['profile_step'] = "age"

        await query.message.reply_text(
            "Твой возраст тоже важен для толкования",
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
            "Бывают ли у тебя осознанные сны (понимаешь, что спишь и можешь влиять на происходящее во сне)?",
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
            "✅ Спасибо!\nТеперь я смогу учитывать ваши ответы в интерпретации снов.",
            reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
        ])
    )
        
    elif query.data == "start_first_dream":
        await query.message.reply_text(
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. Опиши, по возможности, атмосферу и эмоции, которые его сопровождали. Если хочешь, чтобы я учёл положение планет в толковании – укажи дату и примерное место сна (можно по ближайшему крупному городу)\n\nНачнём?"
    )


# --- Инициализация приложения ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
