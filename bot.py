import os
import psycopg2
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)
from openai import AsyncOpenAI

today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
    "You are a qualified dream analyst trained in the methodology of C.G. Jung, with deep knowledge of astrology and esotericism, working within the Western psychological tradition. You interpret dreams as unique messages from the unconscious, drawing on archetypes, symbols, and the collective unconscious. You may reference mythology, astrology, or esoteric concepts metaphorically, if they enrich meaning and maintain internal coherence. Use simple, clear, human language. Avoid quotation marks for symbols and refrain from using specialized terminology. Your task is to identify key images, archetypes, and symbols, and explain their significance for inner development. You do not predict the future, give advice, or act as a therapist. Interpretations must be hypothetical, respectful, and free from rigid or generic meanings. If the user provides the date and location of the dream and requests it, include metaphorical astrological context (e.g. Moon phase, the current planetary positions). If the dream is brief, you may ask 1–3 clarifying questions. If the user declines, interpret only what is available. Maintain a supportive and respectful tone. Match the user's style—concise or detailed, light or deep. Never use obscene language, even if requested; replace it with appropriate, standard synonyms. Do not engage in unrelated topics—gently guide the conversation back to dream analysis. Use only Telegram Markdown formatting (e.g. *bold*, _italic_, `code`) and emojis to illustrate symbols (e.g. 🌑, 👁, 🪞). Do not use HTML. "
"\n\n# User context\n" "Use a paragraph of text to suggest the dream's emotional tone. Try to end your analysis by inviting the user to reflect or respond."   
)

# --- Default menu ---
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        ["🌙 Разобрать мой сон"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
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

# --- Обновление статистики ---
def update_user_stats(user, chat_id: str, message_text: str):
    username = f"@{user.username}" if user.username else None

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_stats (chat_id, username, messages_sent, symbols_sent, updated_at)
            VALUES (%s, %s, 1, %s, now())
            ON CONFLICT (chat_id) DO UPDATE
            SET 
                messages_sent = user_stats.messages_sent + 1,
                symbols_sent = user_stats.symbols_sent + %s,
                username = COALESCE(EXCLUDED.username, user_stats.username),
                updated_at = now()
        """, (
            chat_id,
            username,
            len(message_text),
            len(message_text)
        ))
    conn.commit()

def increment_start_count(user, chat_id: str):
    username = f"@{user.username}" if user.username else None
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_stats (chat_id, username, starts_count, updated_at)
            VALUES (%s, %s, 1, now())
            ON CONFLICT (chat_id) DO UPDATE
            SET 
                starts_count = user_stats.starts_count + 1,
                username = COALESCE(EXCLUDED.username, user_stats.username),
                updated_at = now()
        """, (
            chat_id,
            username
        ))
    conn.commit()


# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    if user_message == "🌙 Разобрать мой сон":
        await start_first_dream_command(update, context)
        return


    log_activity(user, chat_id, "message", user_message)
    log_activity(user, chat_id, "gpt_request", f"model=gpt-4o, temp=0.4, max_tokens={MAX_TOKENS}")

    update_user_stats(user, chat_id, user_message)

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
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    personalized_prompt = DEFAULT_SYSTEM_PROMPT
    personalized_prompt += f"\n\n# Current date\nToday is {today_str}."
    if profile_info:
        personalized_prompt += f"\n\n# User context\n{profile_info.strip()}"


    # Отправка "размышляет"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("〰️ Размышляю...")

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": personalized_prompt}] + history,
            temperature=0.45,
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

    # Логируем событие и увеличиваем счётчик стартов
    log_activity(user, str(chat_id), "start")
    increment_start_count(user, str(chat_id))

    # Inline-кнопки под приветствием
    keyboard = [
        [InlineKeyboardButton("🧾 Познакомимся?", callback_data="start_profile")],
        [InlineKeyboardButton("🔮 Что я умею", callback_data="about")],
        [InlineKeyboardButton("💬 Поделиться впечатлениями", url="https://t.me/dream_sense_chat")],
        [InlineKeyboardButton("💎 Донат на развитие", callback_data="donate")],
        [InlineKeyboardButton("🌙 Разобрать мой сон", callback_data="start_first_dream")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем приветствие с фото и кнопками
    try:
        with open("intro.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=(
                    "💫 Сны – это язык бессознательного. "
                    "Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. "
                    "Но за каждым сном – что-то очень личное, что-то только про тебя.\n\n"
                    "Нажми кнопку ниже или просто начни писать свой сон."
                ),
                reply_markup=MAIN_MENU,
                parse_mode='Markdown'
            )
    
    except FileNotFoundError:
        await update.message.reply_text(
            "💫 Сны – это язык бессознательного. "
            "Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. "
            "Но за каждым сном – что-то очень личное, что-то только про тебя.\n\n"
            "Нажми кнопку ниже или просто начни писать свой сон.",
            reply_markup=MAIN_MENU,
            parse_mode='Markdown'
        )
    

async def start_first_dream_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. "
        "Опиши атмосферу, эмоции, персонажей и, если хочешь, укажи дату и место сна (можно просто город).",
        reply_markup=MAIN_MENU  # чтобы кнопка осталась
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
                caption="💰Спасибо тебе за желание поддержать проект! У нас ещё множество интересных идей для реализации!",
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
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. Опиши, по возможности, атмосферу и эмоции, которые его сопровождали. Если хочешь, чтобы я учёл положение планет в толковании – укажи дату и примерное место сна (можно по ближайшему крупному городу)"
    )


# --- Инициализация приложения ---
if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

from telegram import BotCommand

async def post_init(app):
    try:
        # Очищаем Telegram-меню (≡)
        await app.bot.set_my_commands([])

        # Сбрасываем очередь обновлений (чтобы не было конфликтов)
        await app.bot.get_updates(offset=-1)

        print("✅ Очередь Telegram сброшена, команды очищены.")
        
    except Exception as e:
        print(f"⚠️ Ошибка сброса очереди {e}")


app.post_init = post_init

app.run_polling()
