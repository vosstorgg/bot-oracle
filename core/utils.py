"""
Утилиты для работы с Telegram ботом
"""
import logging

logger = logging.getLogger(__name__)


async def remove_message_buttons_by_id(context, chat_id, message_id):
    """
    Удаляет кнопки из конкретного сообщения по его ID
    
    Args:
        context: Telegram context
        chat_id: ID чата
        message_id: ID сообщения
    """
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
        logger.info(f"🔍 DEBUG: Убрали кнопки из сообщения {message_id}")
        return True
    except Exception as e:
        logger.warning(f"🔍 DEBUG: Не удалось убрать кнопки из сообщения {message_id}: {e}")
        return False


async def remove_message_buttons(context, chat_id, exclude_texts=None):
    """
    Удаляет кнопки из сообщений в чате (fallback метод)
    
    Args:
        context: Telegram context
        chat_id: ID чата
        exclude_texts: Список текстов сообщений, которые нужно исключить
    """
    if exclude_texts is None:
        exclude_texts = []
    
    try:
        updates = await context.bot.get_updates(offset=-1, limit=10)
        buttons_removed = 0
        
        for update in updates:
            if (update.message and 
                update.message.chat.id == int(chat_id) and
                update.message.text and 
                update.message.reply_markup and
                not any(exclude_text in update.message.text for exclude_text in exclude_texts)):
                try:
                    logger.info(f"🔍 DEBUG: Убираем кнопки из сообщения: {update.message.text[:100]}...")
                    await update.message.edit_reply_markup(reply_markup=None)
                    buttons_removed += 1
                    if buttons_removed >= 2:  # Ограничиваем количество
                        break
                except Exception as e:
                    logger.warning(f"🔍 DEBUG: Не удалось убрать кнопки из сообщения: {e}")
                    continue
                    
        return buttons_removed
        
    except Exception as e:
        logger.error(f"🔍 DEBUG: Не удалось получить updates: {e}")
        return 0


async def remove_date_selection_message_by_id(context, chat_id, message_id):
    """
    Удаляет сообщение с выбором даты по его ID
    
    Args:
        context: Telegram context
        chat_id: ID чата
        message_id: ID сообщения
    """
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"🔍 DEBUG: Удалили сообщение с выбором даты {message_id}")
        return True
    except Exception as e:
        logger.warning(f"🔍 DEBUG: Не удалось удалить сообщение с выбором даты {message_id}: {e}")
        return False


async def remove_date_selection_message(context, chat_id):
    """
    Удаляет сообщение "Когда тебе приснился этот сон?" (fallback метод)
    
    Args:
        context: Telegram context
        chat_id: ID чата
    """
    try:
        updates = await context.bot.get_updates(offset=-1, limit=10)
        
        for update in updates:
            if (update.message and 
                update.message.chat.id == int(chat_id) and
                update.message.text and
                "Когда тебе приснился этот сон" in update.message.text):
                try:
                    logger.info(f"🔍 DEBUG: Удаляем сообщение с выбором даты")
                    await update.message.delete()
                    return True
                except Exception as e:
                    logger.warning(f"🔍 DEBUG: Не удалось удалить сообщение с выбором даты: {e}")
                    continue
                    
        return False
        
    except Exception as e:
        logger.error(f"🔍 DEBUG: Не удалось получить updates для удаления сообщения с выбором даты: {e}")
        return False


async def cleanup_astrological_interface_by_ids(context, chat_id, original_message_id=None, date_message_id=None):
    """
    Очищает интерфейс астрологического толкования по ID сообщений (надежный метод)
    
    Args:
        context: Telegram context
        chat_id: ID чата
        original_message_id: ID исходного сообщения с толкованием
        date_message_id: ID сообщения с выбором даты
    """
    success_count = 0
    
    # Убираем кнопки из исходного сообщения
    if original_message_id:
        if await remove_message_buttons_by_id(context, chat_id, original_message_id):
            success_count += 1
    
    # Удаляем сообщение с выбором даты
    if date_message_id:
        if await remove_date_selection_message_by_id(context, chat_id, date_message_id):
            success_count += 1
    
    logger.info(f"🔍 DEBUG: Очистка интерфейса по ID - успешных операций: {success_count}")
    return success_count > 0


async def cleanup_astrological_interface(context, chat_id, current_message_text=""):
    """
    Очищает интерфейс астрологического толкования - убирает кнопки и удаляет сообщение выбора даты (fallback метод)
    
    Args:
        context: Telegram context
        chat_id: ID чата
        current_message_text: Текст текущего сообщения (чтобы исключить его)
    """
    exclude_texts = [
        current_message_text,
        "🔮 Размышляю над астрологическим",
        "Когда тебе приснился этот сон"
    ]
    
    # Убираем кнопки из сообщений
    buttons_removed = await remove_message_buttons(context, chat_id, exclude_texts)
    
    # Удаляем сообщение с выбором даты
    date_message_removed = await remove_date_selection_message(context, chat_id)
    
    logger.info(f"🔍 DEBUG: Очистка интерфейса - убрано кнопок: {buttons_removed}, удалено сообщений с датой: {date_message_removed}")
    
    return buttons_removed > 0 or date_message_removed


def log_error_and_notify(db, user, chat_id, error_type, error_message):
    """
    Логирует ошибку и отправляет уведомление
    
    Args:
        db: Database instance
        user: Telegram user
        chat_id: ID чата
        error_type: Тип ошибки
        error_message: Сообщение об ошибке
    """
    logger.error(f"❌ {error_type}: {error_message}")
    db.log_activity(user, chat_id, error_type, str(error_message))
