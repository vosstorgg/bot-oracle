"""
Обработчики для профиля пользователя и онбординга
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from core.database import db
from core.config import IMAGE_PATHS


async def send_start_menu(chat_id, context, user):
    """Отправка полного стартового меню с фото и кнопками"""
    # Inline-кнопки под приветствием
    keyboard = [
        [InlineKeyboardButton("🧾 Познакомимся?", callback_data="start_profile")],
        [InlineKeyboardButton("🔮 Что я умею", callback_data="about")],
                    [InlineKeyboardButton("💌 Подписаться на канал автора", url="https://t.me/N_W_passage/3")],
        [InlineKeyboardButton("💎 Донат на развитие", callback_data="donate")],
        [InlineKeyboardButton("🌙 Разобрать мой сон", callback_data="start_first_dream")],
        [InlineKeyboardButton("📖 Дневник снов", callback_data="diary_page:0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем приветствие с фото и кнопками
    try:
        with open(IMAGE_PATHS["intro"], "rb") as photo:
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
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "💫 Сны – это язык бессознательного. "
                "Иногда оно шепчет, иногда показывает важное через образы, которые сложно понять с первого взгляда. "
                "Но за каждым сном – что-то очень личное, что-то только про тебя."
            ),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    from core.config import MAIN_MENU
    
    chat_id = update.effective_chat.id
    user = update.effective_user

    # Логируем событие и увеличиваем счётчик стартов
    db.log_activity(user, str(chat_id), "start")
    db.increment_start_count(user, str(chat_id))

    # Отправляем полное стартовое меню
    await send_start_menu(chat_id, context, user)
    
    # Добавляем кнопочное меню снизу
    await update.message.reply_text(
        text="Просто опиши свой сон и я начну трактование",
        reply_markup=MAIN_MENU
    )


async def handle_profile_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработка callback'ов связанных с профилем"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    if callback_data == "start_profile":
        try:
            with open(IMAGE_PATHS["quiz"], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption="🧾 Всего 3 коротких вопроса, которые помогут мне лучше трактовать твои сны.\n\nНачнём?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Начинаем", callback_data="profile_step:gender")],
                        [InlineKeyboardButton("Давай не сейчас", callback_data="profile_step:skip")]
                    ])
                )
        except FileNotFoundError:
            await query.message.reply_text(
                "🧾 Всего 3 коротких вопроса, которые помогут мне лучше трактовать твои сны.\n\nНачнём?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Начинаем", callback_data="profile_step:gender")],
                    [InlineKeyboardButton("Давай не сейчас", callback_data="profile_step:skip")]
                ])
            )
    
    elif callback_data == "profile_step:gender":
        context.user_data['profile_step'] = "gender"
        await query.message.reply_text(
            "Символика снов у женщин и мужчин немного отличается. Ты:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Женщина", callback_data="gender:female")],
                [InlineKeyboardButton("Мужчина", callback_data="gender:male")],
                [InlineKeyboardButton("Не скажу", callback_data="gender:other")]
            ])
        )
    
    elif callback_data == "profile_step:skip":
        await query.message.reply_text("Хорошо! Вы всегда можете вернуться к анкете позже через команду /start.")
    
    elif callback_data.startswith("gender:"):
        gender = callback_data.split(":")[1]
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
    
    elif callback_data.startswith("age:"):
        age = callback_data.split(":")[1]
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
    
    elif callback_data.startswith("lucid:"):
        lucid = callback_data.split(":")[1]
        context.user_data['lucid_dreaming'] = lucid
        context.user_data['profile_step'] = None

        # Сохраняем профиль в БД
        db.save_user_profile(
            chat_id=chat_id,
            username=f"@{user.username}" if user.username else None,
            gender=context.user_data.get('gender'),
            age_group=context.user_data.get('age_group'),
            lucid_dreaming=lucid
        )

        await query.message.reply_text(
            "✅ Спасибо!\nТеперь я смогу учитывать твои ответы в интерпретации снов.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
            ])
        )


async def handle_info_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработка информационных callback'ов"""
    query = update.callback_query
    
    if callback_data == "about":
        try:
            with open(IMAGE_PATHS["about"], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=(
                        "Я – чат-бот, который помогает тебе понять свои сны. Моя основа — психологический анализ, прежде всего методика Карла Юнга. "
                        "Мне можно рассказать любой сон – даже самый короткий, запутанный или необычный – и узнать, что хочет подсказать тебе твоё подсознание.\n\n"
                        "Я бережно помогаю, не осуждаю и не даю готовых ответов, не навязываю смыслов. Я просто рядом — чтобы помочь тебе чуть ближе подойти к себе, "
                        "к своему внутреннему знанию, к тому, что обычно остаётся в тени.\n\n"
                        "Вот что я умею:\n"
                        "🌙 Толкую сны с опорой на образы, архетипы и символы\n"
                        "💬 Учитываю стиль общения, в котором тебе комфортно – кратко или развернуто, серьёзно или с лёгкостью\n"
                        "🦄 Могу обсудить с тобой символику сна более подробно и ответить на вопросы\n"
                        "🪐По запросу – учитываю дату и место сна, чтобы добавить астрологический контекст, исходя из положения планет в это время\n"
                        "🕊️Говорю с тобой бережно и помогаю взглянуть на сон, как на путь к пониманию себя\n\n"
                        "Если хочешь – просто расскажи свой сон. Я здесь, чтобы слушать и истолковывать"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
                    ])
                )
        except FileNotFoundError:
            await query.message.reply_text(
                "Я – чат-бот, который помогает тебе понять свои сны...",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌙 Рассказать свой сон", callback_data="start_first_dream")]
                ])
            )
    
    elif callback_data == "donate":
        from core.config import LINKS
        
        try:
            with open(IMAGE_PATHS["donate"], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption="💰Спасибо тебе за желание поддержать проект! У нас ещё множество интересных идей для реализации!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Задонатить!", url=LINKS["donation"])]
                    ])
                )
        except FileNotFoundError:
            await query.message.reply_text(
                "💰Спасибо тебе за желание поддержать проект! У нас ещё множество интересных идей для реализации!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Задонатить!", url=LINKS["donation"])]
                ])
            )
    
    elif callback_data == "start_first_dream":
        await query.message.reply_text(
            "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. "
            "Опиши, по возможности, атмосферу и эмоции, которые его сопровождали. Если хочешь, чтобы я учёл положение планет в толковании – "
            "укажи дату и примерное место сна (можно по ближайшему крупному городу)"
        )
