"""
Обработчики для дневника снов
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from core.database import db
from core.models import PaginationHelper, MessageFormatter
from core.config import PAGINATION


async def show_dream_diary(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показать дневник снов пользователя"""
    from core.config import IMAGE_PATHS
    
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Получаем общее количество снов
    total_dreams = db.count_user_dreams(chat_id)
    
    if total_dreams == 0:
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        
        caption = (
            "Здесь хранятся все твои сны и их толкования. Каждый сон, который ты мне рассказываешь (текстом или голосом), "
            "автоматически сохраняется в дневник вместе с моей интерпретацией.\n\n"
            "У тебя пока нет записанных снов. Расскажи мне свой сон, и он появится здесь!"
        )
        
        try:
            with open(IMAGE_PATHS["diary"], "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except FileNotFoundError:
            await update.message.reply_text(
                caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return
    
    # Вычисляем пагинацию
    pagination = PaginationHelper.calculate_pagination(
        total_dreams, page, PAGINATION["dreams_per_page"]
    )
    
    # Получаем сны для текущей страницы
    dreams = db.get_user_dreams(chat_id, pagination["items_per_page"], pagination["offset"])
    
    # Формируем caption с описанием
    caption = (
        "Здесь хранятся все твои сны и их толкования. Нажми на любой сон, чтобы прочитать его полностью."
    )
    
    if pagination["total_pages"] > 1:
        caption += f"\n\nСтр. {pagination['current_page'] + 1} из {pagination['total_pages']}"
    
    keyboard = []
    
    for i, dream in enumerate(dreams):
        dream_id, dream_text, interpretation, astrological_interpretation, source_type, created_at, dream_date = dream
        
        # Краткое описание для кнопки
        dream_preview = MessageFormatter.format_dream_preview(dream_text, 35)
        source_icon = MessageFormatter.get_source_icon(source_type)
        date_str = MessageFormatter.format_date(created_at)
        
        button_text = f"{source_icon} {date_str} • {dream_preview}"
        
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"dream_view:{dream_id}"
        )])
    
    # Кнопки навигации
    nav_buttons = []
    if pagination["has_prev"]:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"diary_page:{pagination['current_page']-1}"))
    if pagination["has_next"]:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"diary_page:{pagination['current_page']+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    try:
        with open(IMAGE_PATHS["diary"], "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except FileNotFoundError:
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def show_dream_diary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показать дневник снов через callback (с редактированием)"""
    from core.config import IMAGE_PATHS
    
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    # Получаем общее количество снов
    total_dreams = db.count_user_dreams(chat_id)
    
    if total_dreams == 0:
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        
        caption = (
            "Здесь хранятся все твои сны и их толкования. Каждый сон, который ты мне рассказываешь (текстом или голосом), "
            "автоматически сохраняется в дневник вместе с моей интерпретацией.\n\n"
            "У тебя пока нет записанных снов. Расскажи мне свой сон, и он появится здесь!"
        )
        
        # Удаляем старое сообщение и отправляем новое с фото
        try:
            await query.delete_message()
        except Exception:
            pass
        
        try:
            with open(IMAGE_PATHS["diary"], "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except FileNotFoundError:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        return
    
    # Вычисляем пагинацию
    pagination = PaginationHelper.calculate_pagination(
        total_dreams, page, PAGINATION["dreams_per_page"]
    )
    
    # Получаем сны для текущей страницы
    dreams = db.get_user_dreams(chat_id, pagination["items_per_page"], pagination["offset"])
    
    # Формируем caption с описанием
    caption = (
        "Здесь хранятся все твои сны и их толкования. Нажми на любой сон, чтобы прочитать его полностью."
    )
    
    if pagination["total_pages"] > 1:
        caption += f"\n\nСтр. {pagination['current_page'] + 1} из {pagination['total_pages']}"
    
    keyboard = []
    
    for i, dream in enumerate(dreams):
        dream_id, dream_text, interpretation, source_type, created_at, dream_date = dream
        
        # Краткое описание для кнопки
        dream_preview = MessageFormatter.format_dream_preview(dream_text, 35)
        source_icon = MessageFormatter.get_source_icon(source_type)
        date_str = MessageFormatter.format_date(created_at)
        
        button_text = f"{source_icon} {date_str} • {dream_preview}"
        
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"dream_view:{dream_id}"
        )])
    
    # Кнопки навигации
    nav_buttons = []
    if pagination["has_prev"]:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"diary_page:{pagination['current_page']-1}"))
    if pagination["has_next"]:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"diary_page:{pagination['current_page']+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    # Удаляем старое сообщение и отправляем новое с фото
    try:
        await query.delete_message()
    except Exception:
        pass
    
    try:
        with open(IMAGE_PATHS["diary"], "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except FileNotFoundError:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def show_dream_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, dream_id: int):
    """Показать детали конкретного сна"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    # Получаем сон из БД
    dream = db.get_dream_by_id(chat_id, dream_id)
    
    if not dream:
        await query.answer("❌ Сон не найден")
        return
    
    dream_id, dream_text, interpretation, astrological_interpretation, source_type, created_at, dream_date = dream
    
    # Формируем иконку источника
    source_icon = MessageFormatter.get_source_description(source_type)
    
    # Форматируем дату
    date_str = MessageFormatter.format_datetime(created_at)
    
    # Формируем сообщение с полным содержанием
    message_text = (
        f"📖 *Сон от {date_str}*\n"
        f"{source_icon}\n\n"
        f"*💭 Описание сна:*\n\n{dream_text}\n\n"
        f"*✨ Толкование:*\n\n{interpretation}"
    )
    
    # Добавляем астрологическое толкование, если оно есть
    if astrological_interpretation:
        message_text += f"\n\n*🔮 Астрологическое толкование:*\n\n{astrological_interpretation}"
    
    # Обрезаем если слишком длинный
    message_text = MessageFormatter.truncate_message(message_text, PAGINATION["max_message_length"])
    
    # Кнопки управления
    keyboard = [
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"dream_delete:{dream_id}"),
            InlineKeyboardButton("◀️ К дневнику", callback_data="diary_page:0")
        ]
    ]
    
    try:
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except BadRequest:
        # Если сообщение содержит фото и не может быть отредактировано как текст
        try:
            await query.delete_message()
        except Exception:
            pass
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def delete_dream_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, dream_id: int):
    """Подтверждение удаления сна"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    # Получаем сон для отображения превью
    dream = db.get_dream_by_id(chat_id, dream_id)
    
    if not dream:
        await query.answer("❌ Сон не найден")
        return
    
    dream_id, dream_text, interpretation, astrological_interpretation, source_type, created_at, dream_date = dream
    date_str = MessageFormatter.format_date(created_at)
    dream_preview = MessageFormatter.format_dream_preview(dream_text, 100)
    
    message_text = (
        f"🗑 *Удаление сна*\n\n"
        f"*Дата:* {date_str}\n"
        f"*Сон:* {dream_preview}\n\n"
        f"Точно удалить этот сон? Это действие нельзя отменить."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("❌ Да, удалить", callback_data=f"dream_delete_yes:{dream_id}"),
            InlineKeyboardButton("◀️ Отмена", callback_data=f"dream_view:{dream_id}")
        ]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def delete_dream_execute(update: Update, context: ContextTypes.DEFAULT_TYPE, dream_id: int):
    """Выполнение удаления сна"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Удаляем сон
    success = db.delete_dream(chat_id, dream_id)
    
    if success:
        db.log_activity(user, chat_id, "dream_deleted", f"dream_id:{dream_id}")
        await query.answer("✅ Сон удален")
        # Возвращаемся к дневнику
        await show_dream_diary_callback(update, context, 0)
    else:
        await query.answer("❌ Ошибка при удалении сна")


async def handle_diary_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработка всех callback'ов дневника снов"""
    
    if callback_data.startswith("diary_page:"):
        page = int(callback_data.split(":")[1])
        await show_dream_diary_callback(update, context, page)
    
    elif callback_data.startswith("dream_view:"):
        dream_id = int(callback_data.split(":")[1])
        await show_dream_detail(update, context, dream_id)
    
    elif callback_data.startswith("dream_delete:") and not callback_data.startswith("dream_delete_yes:"):
        dream_id = int(callback_data.split(":")[1])
        await delete_dream_confirm(update, context, dream_id)
    
    elif callback_data.startswith("dream_delete_yes:"):
        dream_id = int(callback_data.split(":")[1])
        await delete_dream_execute(update, context, dream_id)
