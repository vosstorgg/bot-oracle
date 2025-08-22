import os
import asyncio
import psycopg2
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest, NetworkError
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

# --- Инициализация таблиц ---
def init_tables():
    """Инициализация необходимых таблиц"""
    with conn.cursor() as cur:
        # Таблица статистики пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                chat_id VARCHAR(20) PRIMARY KEY,
                username VARCHAR(100),
                messages_sent INTEGER DEFAULT 0,
                symbols_sent INTEGER DEFAULT 0,
                starts_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Таблица логов активности
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username VARCHAR(100),
                chat_id VARCHAR(20),
                action VARCHAR(50),
                content TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Таблица сообщений
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR(20) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Индекс для быстрого поиска истории
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_timestamp 
            ON messages (chat_id, timestamp DESC)
        """)
        
        # Таблица профилей пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                chat_id VARCHAR(20) PRIMARY KEY,
                username VARCHAR(100),
                gender VARCHAR(20),
                age_group VARCHAR(20),
                lucid_dreaming VARCHAR(20),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    
    conn.commit()
    print("✅ Таблицы инициализированы")

# Инициализируем таблицы при запуске
init_tables()

MAX_TOKENS = 1400
MAX_HISTORY = 10

# --- Настройки админов ---
# ADMIN_CHAT_ID - переменная окружения с ID админов, разделенными запятыми
# Поддерживает как одного админа, так и нескольких (через запятые)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "234526032")
ADMIN_CHAT_IDS = ADMIN_CHAT_ID.split(",") if ADMIN_CHAT_ID else []
ADMIN_CHAT_IDS = [chat_id.strip() for chat_id in ADMIN_CHAT_IDS if chat_id.strip()]

# --- Состояния админов для broadcast ---
admin_broadcast_states = {}

# --- Default system prompt ---
DEFAULT_SYSTEM_PROMPT = (
    "You are a qualified dream analyst trained in the methodology of C.G. Jung, with deep knowledge of astrology and esotericism, working within the Western psychological tradition. You interpret dreams as unique messages from the unconscious, drawing on archetypes, symbols, and the collective unconscious. You may reference mythology, astrology, or esoteric concepts metaphorically, if they enrich meaning and maintain internal coherence. Use simple, clear, human language. Avoid quotation marks for symbols and refrain from using specialized terminology. Your task is to identify key images, archetypes, and symbols, and explain their significance for inner development. You do not predict the future, give advice, or act as a therapist. Interpretations must be hypothetical, respectful, and free from rigid or generic meanings. If the user provides the date and location of the dream and requests it, include metaphorical astrological context (e.g. Moon phase, the current planetary positions). If the dream is brief, you may ask 1–3 clarifying questions. If the user declines, interpret only what is available. Maintain a supportive and respectful tone. Match the user's style—concise or detailed, light or deep. Never use obscene language, even if requested; replace it with appropriate, standard synonyms. Do not engage in unrelated topics—gently guide the conversation back to dream analysis. Use only Telegram Markdown formatting (e.g. *bold*, _italic_, `code`) and emojis to illustrate symbols (e.g. 🌑, 👁, 🪞). Do not use HTML. "
"\n\n# User context\n" "Use a paragraph of text to suggest the dream's emotional tone. Try to end your analysis by inviting the user to reflect or respond. Speak Russian using informal 'ты' form with users."   
)

# --- Default menu ---
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        ["🌙 Разобрать мой сон"],
        ["💬 Подписаться на канал автора"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)


# --- Лог активности ---
def log_activity(user, chat_id, action, content=""):
    try:
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
    except Exception as e:
        print(f"❌ Ошибка логирования активности: {e}")
        # Сбрасываем транзакцию при ошибке
        conn.rollback()

# --- Обновление статистики ---
def update_user_stats(user, chat_id: str, message_text: str):
    username = f"@{user.username}" if user.username else None

    try:
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
    except Exception as e:
        print(f"❌ Ошибка обновления статистики: {e}")
        conn.rollback()

def increment_start_count(user, chat_id: str):
    username = f"@{user.username}" if user.username else None
    try:
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
    except Exception as e:
        print(f"❌ Ошибка обновления счетчика стартов: {e}")
        conn.rollback()


# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Проверяем, ждет ли админ контент для рассылки
    if chat_id in admin_broadcast_states and admin_broadcast_states[chat_id].get("waiting_for_content"):
        await handle_admin_broadcast_content(update, context)
        return
    
    # Проверяем, подтверждает ли админ рассылку
    if chat_id in admin_broadcast_states and admin_broadcast_states[chat_id].get("waiting_for_confirmation"):
        await handle_admin_broadcast_confirmation(update, context)
        return
    
    # Получаем текст сообщения (может быть из text или caption для медиа)
    user_message = ""
    if update.message.text:
        user_message = update.message.text
    elif update.message.caption:
        user_message = update.message.caption
    
    if user_message == "🌙 Разобрать мой сон":
        await start_first_dream_command(update, context)
        return

    if user_message == "💬 Подписаться на канал автора":
        await channel_view_command(update, context)
        return

    # Для обычных пользователей - обрабатываем только текстовые описания снов
    if not user_message:
        await update.message.reply_text(
            "🤔 Я анализирую только текстовые описания снов. Расскажи мне свой сон словами, и я помогу его понять.",
            reply_markup=MAIN_MENU
        )
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
        [InlineKeyboardButton("💬 Подписаться на канал автора", url="https://t.me/N_W_passage")],
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
                    "Но за каждым сном – что-то очень личное, что-то только про тебя."
                ),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    except FileNotFoundError:
        await update.message.reply_text(
            "💫 Сны – это язык бессознательного. "
            "Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. "
            "Но за каждым сном – что-то очень личное, что-то только про тебя.",
            
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    await update.message.reply_text(
        text="Просто опиши свой сон и я начну трактование",
        reply_markup=MAIN_MENU
    )

async def start_first_dream_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. "
        "Опиши атмосферу, эмоции, персонажей и, если хочешь, укажи дату и место сна (можно просто город).",
        reply_markup=MAIN_MENU 
    )

async def channel_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Лучшая поддержка сейчас — подписаться на канал автора.\n\nСпасибо! ❤️",
        
        reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Подписаться на канал", url="https://t.me/N_W_passage")]
                ])
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
            "✅ Спасибо!\nТеперь я смогу учитывать твои ответы в интерпретации снов.",
            reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
        ])
    )
        
    elif query.data == "start_first_dream":
        await query.message.reply_text(
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. Опиши, по возможности, атмосферу и эмоции, которые его сопровождали. Если хочешь, чтобы я учёл положение планет в толковании – укажи дату и примерное место сна (можно по ближайшему крупному городу)"
    )
    
    # Админские callback'и
    elif query.data == "admin_broadcast":
        await admin_broadcast_callback(update, context)
    
    elif query.data == "admin_stats":
        # Статистика пользователей  
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN updated_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as active_24h,
                    COUNT(CASE WHEN updated_at >= NOW() - INTERVAL '7 days' THEN 1 END) as active_7d,
                    SUM(messages_sent) as total_messages
                FROM user_stats
            """)
            stats = cur.fetchone()
        
        if stats:
            total, active_24h, active_7d, total_messages = stats
            await query.edit_message_text(
                f"📊 *Статистика пользователей*\n\n"
                f"👥 Всего пользователей: {total or 0}\n"
                f"🟢 Активных за 24ч: {active_24h or 0}\n"
                f"📅 Активных за 7 дней: {active_7d or 0}\n"
                f"💬 Всего сообщений: {total_messages or 0}",
                parse_mode='Markdown'
            )
    
    elif query.data == "admin_activity":
        # Последняя активность
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT action, COUNT(*) as count
                    FROM user_activity_log 
                    WHERE timestamp >= NOW() - INTERVAL '24 hours'
                    GROUP BY action
                    ORDER BY count DESC
                    LIMIT 10
                """)
                activities = cur.fetchall()
            
            if activities:
                activity_text = "\n".join([f"• {action}: {count}" for action, count in activities])
                await query.edit_message_text(
                    f"📋 *Активность за 24 часа*\n\n{activity_text}",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("📋 Нет активности за последние 24 часа.")
        except Exception as e:
            print(f"❌ Ошибка получения активности: {e}")
            await query.edit_message_text("📋 Ошибка при получении данных активности.")
    
    # Обработчики подтверждения рассылки
    elif query.data == "broadcast_confirm_yes":
        await handle_broadcast_confirm_yes(update, context)
    
    elif query.data == "broadcast_confirm_no":
        await handle_broadcast_confirm_no(update, context)


# --- Функции для broadcast ---

def get_all_users():
    """Получить список всех пользователей из базы данных"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT chat_id 
                FROM user_stats 
                WHERE chat_id IS NOT NULL 
                GROUP BY chat_id
                ORDER BY MAX(updated_at) DESC
            """)
            users = cur.fetchall()
            return [str(user[0]) for user in users]
    except Exception as e:
        print(f"❌ Ошибка получения пользователей: {e}")
        return []

async def send_broadcast_message_content(context, chat_id: str, content_data):
    """Отправить контент (текст, фото, документ и т.д.) одному пользователю"""
    try:
        if content_data["type"] == "text":
            await context.bot.send_message(
                chat_id=chat_id,
                text=content_data["text"],
                parse_mode='Markdown'
            )
        elif content_data["type"] == "photo":
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=content_data["file_id"],
                caption=content_data.get("caption", ""),
                parse_mode='Markdown'
            )
        elif content_data["type"] == "document":
            await context.bot.send_document(
                chat_id=chat_id,
                document=content_data["file_id"],
                caption=content_data.get("caption", ""),
                parse_mode='Markdown'
            )
        elif content_data["type"] == "video":
            await context.bot.send_video(
                chat_id=chat_id,
                video=content_data["file_id"],
                caption=content_data.get("caption", ""),
                parse_mode='Markdown'
            )
        elif content_data["type"] == "audio":
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=content_data["file_id"],
                caption=content_data.get("caption", ""),
                parse_mode='Markdown'
            )
        elif content_data["type"] == "voice":
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=content_data["file_id"],
                caption=content_data.get("caption", ""),
                parse_mode='Markdown'
            )
        elif content_data["type"] == "sticker":
            await context.bot.send_sticker(
                chat_id=chat_id,
                sticker=content_data["file_id"]
            )
        
        return {"status": "success", "chat_id": chat_id}
    except Forbidden:
        return {"status": "blocked", "chat_id": chat_id}
    except BadRequest:
        return {"status": "error", "chat_id": chat_id}
    except NetworkError:
        return {"status": "network_error", "chat_id": chat_id}
    except Exception as e:
        return {"status": "unknown_error", "chat_id": chat_id, "error": str(e)}

async def send_broadcast_message(context, chat_id: str, message: str):
    """Отправить текстовое сообщение (для обратной совместимости)"""
    return await send_broadcast_message_content(context, chat_id, {
        "type": "text",
        "text": message
    })

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда массовой рассылки для админов"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Проверка прав админа
    if chat_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Логируем использование команды
    log_activity(user, chat_id, "broadcast_command", "admin used broadcast")
    
    # Проверяем, что есть текст для рассылки
    if not context.args:
        await update.message.reply_text(
            "📢 *Команда массовой рассылки*\n\n"
            "Использование: `/broadcast <сообщение>`\n\n"
            "Пример: `/broadcast Привет! У нас новые функции в боте!`",
            parse_mode='Markdown'
        )
        return
    
    # Собираем текст сообщения
    broadcast_text = " ".join(context.args)
    
    # Получаем список пользователей
    users = get_all_users()
    total_users = len(users)
    
    if total_users == 0:
        await update.message.reply_text("📭 Нет пользователей для рассылки.")
        return
    
    # Отправляем уведомление о начале рассылки
    progress_msg = await update.message.reply_text(
        f"📡 *Начинаю рассылку...*\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📝 Сообщение: `{broadcast_text[:100]}{'...' if len(broadcast_text) > 100 else ''}`",
        parse_mode='Markdown'
    )
    
    # Счетчики результатов
    results = {
        "success": 0,
        "blocked": 0, 
        "error": 0,
        "network_error": 0,
        "unknown_error": 0
    }
    
    # Отправляем сообщения с rate limiting
    for i, user_chat_id in enumerate(users, 1):
        result = await send_broadcast_message(context, user_chat_id, broadcast_text)
        results[result["status"]] += 1
        
        # Обновляем прогресс каждые 50 сообщений
        if i % 50 == 0 or i == total_users:
            await progress_msg.edit_text(
                f"📡 *Рассылка в процессе...*\n\n"
                f"📊 Прогресс: {i}/{total_users}\n"
                f"✅ Успешно: {results['success']}\n"
                f"🚫 Заблокировали: {results['blocked']}\n"
                f"❌ Ошибки: {results['error'] + results['network_error'] + results['unknown_error']}",
                parse_mode='Markdown'
            )
        
        # Rate limiting - 30 сообщений в секунду максимум для Telegram
        await asyncio.sleep(0.05)
    
    # Итоговый отчет
    await progress_msg.edit_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📊 **Статистика:**\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Доставлено: {results['success']}\n"
        f"🚫 Заблокировали бота: {results['blocked']}\n"
        f"❌ Ошибки отправки: {results['error']}\n"
        f"🌐 Сетевые ошибки: {results['network_error']}\n"
        f"❓ Неизвестные ошибки: {results['unknown_error']}\n\n"
        f"📈 Успешность: {(results['success']/total_users*100):.1f}%",
        parse_mode='Markdown'
    )
    
    # Логируем результаты
    log_activity(user, chat_id, "broadcast_completed", 
                f"sent to {results['success']}/{total_users} users")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда админ-панели для доступа к административным функциям"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Проверка прав админа
    if chat_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    log_activity(user, chat_id, "admin_panel", "admin accessed admin panel")
    
    # Админ-панель с inline кнопками
    keyboard = [
        [InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Статистика пользователей", callback_data="admin_stats")],
        [InlineKeyboardButton("📋 Активность бота", callback_data="admin_activity")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔐 *Панель администратора*\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки массовой рассылки в админ-панели"""
    query = update.callback_query
    await query.answer()
    
    chat_id = str(update.effective_chat.id)
    
    # Проверка прав админа
    if chat_id not in ADMIN_CHAT_IDS:
        await query.edit_message_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Устанавливаем состояние ожидания сообщения для рассылки
    admin_broadcast_states[chat_id] = {"waiting_for_content": True}
    
    await query.edit_message_text(
        "📢 *Подготовка массовой рассылки*\n\n"
        "Отправьте сообщение (текст, фото, документ, видео и т.д.), которое хотите разослать всем пользователям.\n\n"
        "✨ *Поддерживаются:*\n"
        "• 📝 Текстовые сообщения\n"
        "• 📷 Фотографии с подписями\n"
        "• 🎥 Видео с подписями\n"
        "• 📄 Документы\n"
        "• 🎵 Аудио\n"
        "• 🗣 Голосовые\n"
        "• 😊 Стикеры\n\n"
        "💡 *Для отмены* отправьте `/cancel`",
        parse_mode='Markdown'
    )

async def handle_admin_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения контента для массовой рассылки"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    message = update.message
    
    # Проверка команды отмены
    if message.text and message.text.strip() == "/cancel":
        admin_broadcast_states.pop(chat_id, None)
        await message.reply_text(
            "❌ Рассылка отменена.",
            parse_mode='Markdown'
        )
        return
    
    # Определяем тип контента и сохраняем
    content_data = None
    preview_text = ""
    
    if message.text:
        content_data = {
            "type": "text",
            "text": message.text
        }
        preview_text = f"📝 *Текст:* {message.text[:100]}{'...' if len(message.text) > 100 else ''}"
        
    elif message.photo:
        content_data = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or ""
        }
        preview_text = f"📷 *Фото* {('с подписью: ' + message.caption[:50] + '...') if message.caption and len(message.caption) > 50 else ('с подписью: ' + message.caption) if message.caption else ''}"
        
    elif message.document:
        content_data = {
            "type": "document", 
            "file_id": message.document.file_id,
            "caption": message.caption or ""
        }
        preview_text = f"📄 *Документ:* {message.document.file_name or 'файл'} {('с подписью: ' + message.caption[:50] + '...') if message.caption and len(message.caption) > 50 else ('с подписью: ' + message.caption) if message.caption else ''}"
        
    elif message.video:
        content_data = {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption or ""
        }
        preview_text = f"🎥 *Видео* {('с подписью: ' + message.caption[:50] + '...') if message.caption and len(message.caption) > 50 else ('с подписью: ' + message.caption) if message.caption else ''}"
        
    elif message.audio:
        content_data = {
            "type": "audio",
            "file_id": message.audio.file_id,
            "caption": message.caption or ""
        }
        preview_text = f"🎵 *Аудио* {('с подписью: ' + message.caption[:50] + '...') if message.caption and len(message.caption) > 50 else ('с подписью: ' + message.caption) if message.caption else ''}"
        
    elif message.voice:
        content_data = {
            "type": "voice",
            "file_id": message.voice.file_id,
            "caption": message.caption or ""
        }
        preview_text = f"🗣 *Голосовое сообщение* {('с подписью: ' + message.caption[:50] + '...') if message.caption and len(message.caption) > 50 else ('с подписью: ' + message.caption) if message.caption else ''}"
        
    elif message.sticker:
        content_data = {
            "type": "sticker",
            "file_id": message.sticker.file_id
        }
        preview_text = f"😊 *Стикер*"
    
    if not content_data:
        await message.reply_text(
            "❌ Неподдерживаемый тип контента. Отправьте текст, фото, документ, видео, аудио, голосовое сообщение или стикер.",
            parse_mode='Markdown'
        )
        return
    
    # Сохраняем контент и переходим к подтверждению
    admin_broadcast_states[chat_id] = {
        "waiting_for_confirmation": True,
        "content": content_data,
        "preview": preview_text
    }
    
    log_activity(user, chat_id, "broadcast_content_prepared", f"type: {content_data['type']}")
    
    # Получаем количество пользователей
    users = get_all_users()
    total_users = len(users)
    
    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да, отправить всем", callback_data="broadcast_confirm_yes")],
        [InlineKeyboardButton("❌ Отменить", callback_data="broadcast_confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        f"📡 *Подтверждение массовой рассылки*\n\n"
        f"*Контент для рассылки:*\n{preview_text}\n\n"
        f"👥 *Количество получателей:* {total_users}\n\n"
        f"⚠️ *Вы уверены, что хотите отправить это сообщение всем пользователям?*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_admin_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового подтверждения (если пользователь не использует кнопки)"""
    chat_id = str(update.effective_chat.id)
    message = update.message
    
    if message.text and message.text.strip().lower() in ["/cancel", "отмена", "нет", "no"]:
        admin_broadcast_states.pop(chat_id, None)
        await message.reply_text("❌ Рассылка отменена.")
    else:
        await message.reply_text(
            "❓ Используйте кнопки выше для подтверждения или отправьте `/cancel` для отмены.",
            parse_mode='Markdown'
        )

async def handle_broadcast_confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения отправки рассылки"""
    query = update.callback_query
    await query.answer()
    
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Проверяем состояние и права
    if (chat_id not in admin_broadcast_states or 
        not admin_broadcast_states[chat_id].get("waiting_for_confirmation") or
        chat_id not in ADMIN_CHAT_IDS):
        await query.edit_message_text("❌ Ошибка: состояние рассылки не найдено или нет прав.")
        return
    
    # Получаем данные для рассылки
    broadcast_data = admin_broadcast_states[chat_id]
    content_data = broadcast_data["content"]
    preview_text = broadcast_data["preview"]
    
    # Очищаем состояние
    admin_broadcast_states.pop(chat_id, None)
    
    # Получаем список пользователей
    users = get_all_users()
    total_users = len(users)
    
    if total_users == 0:
        await query.edit_message_text("📭 Нет пользователей для рассылки.")
        return
    
    # Логируем начало рассылки
    log_activity(user, chat_id, "broadcast_started", f"type: {content_data['type']}, users: {total_users}")
    
    # Отправляем уведомление о начале рассылки
    progress_msg = await query.edit_message_text(
        f"📡 *Начинаю массовую рассылку...*\n\n"
        f"*Контент:* {preview_text}\n"
        f"👥 Всего пользователей: {total_users}\n\n"
        f"⏳ Отправка в процессе...",
        parse_mode='Markdown'
    )
    
    # Счетчики результатов
    results = {
        "success": 0,
        "blocked": 0, 
        "error": 0,
        "network_error": 0,
        "unknown_error": 0
    }
    
    # Отправляем сообщения с rate limiting
    for i, user_chat_id in enumerate(users, 1):
        result = await send_broadcast_message_content(context, user_chat_id, content_data)
        results[result["status"]] += 1
        
        # Обновляем прогресс каждые 50 сообщений
        if i % 50 == 0 or i == total_users:
            try:
                await progress_msg.edit_text(
                    f"📡 *Рассылка в процессе...*\n\n"
                    f"*Контент:* {preview_text}\n"
                    f"📊 Прогресс: {i}/{total_users}\n"
                    f"✅ Успешно: {results['success']}\n"
                    f"🚫 Заблокировали: {results['blocked']}\n"
                    f"❌ Ошибки: {results['error'] + results['network_error'] + results['unknown_error']}",
                    parse_mode='Markdown'
                )
            except:
                pass  # Игнорируем ошибки обновления прогресса
        
        # Rate limiting - 30 сообщений в секунду максимум для Telegram
        await asyncio.sleep(0.05)
    
    # Итоговый отчет
    try:
        await progress_msg.edit_text(
            f"✅ *Массовая рассылка завершена!*\n\n"
            f"*Контент:* {preview_text}\n\n"
            f"📊 **Итоговая статистика:**\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Доставлено: {results['success']}\n"
            f"🚫 Заблокировали бота: {results['blocked']}\n"
            f"❌ Ошибки отправки: {results['error']}\n"
            f"🌐 Сетевые ошибки: {results['network_error']}\n"
            f"❓ Неизвестные ошибки: {results['unknown_error']}\n\n"
            f"📈 Успешность: {(results['success']/total_users*100):.1f}%",
            parse_mode='Markdown'
        )
    except:
        # Если не удалось обновить сообщение, отправляем новое
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Рассылка завершена! Доставлено {results['success']}/{total_users} ({(results['success']/total_users*100):.1f}%)"
        )
    
    # Логируем результаты
    log_activity(user, chat_id, "broadcast_completed", 
                f"sent to {results['success']}/{total_users} users, type: {content_data['type']}")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда отмены для админов"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id in admin_broadcast_states:
        admin_broadcast_states.pop(chat_id, None)
        await update.message.reply_text(
            "❌ Операция рассылки отменена.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "ℹ️ Нет активных операций для отмены.",
            parse_mode='Markdown'
        )

async def handle_broadcast_confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены рассылки"""
    query = update.callback_query
    await query.answer()
    
    chat_id = str(update.effective_chat.id)
    
    # Очищаем состояние
    admin_broadcast_states.pop(chat_id, None)
    
    await query.edit_message_text(
        "❌ *Рассылка отменена*\n\nСообщение не было отправлено пользователям.",
        parse_mode='Markdown'
    )
