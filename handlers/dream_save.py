"""
Обработчики для сохранения снов в дневник
"""
import logging
from core.utils import cleanup_astrological_interface
from core.error_handler import handle_errors, validate_pending_dream, safe_callback_data_split, DatabaseError

logger = logging.getLogger(__name__)


@handle_errors("dream_save")
async def handle_save_dream_callback(update, context, callback_data):
    """Обработчик кнопки 'Сохранить в дневник снов'"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    # Получаем данные сна из временного хранилища в БД
    from core.database import db
    
    # Валидируем входные данные
    parts = safe_callback_data_split(callback_data, 2)
    source_type = parts[1]
    
    # Валидируем существование pending_dream
    pending_dream = await validate_pending_dream(db, chat_id)
    logger.info(f"🔍 DEBUG: pending_dream из БД = {pending_dream}")
    
    # Проверяем, есть ли астрологическое толкование
    has_astrological = pending_dream.get('astrological_interpretation') is not None
    
    # Сохраняем сон в дневник
    dream_saved = await save_dream_to_diary(
        db, chat_id, pending_dream, source_type, has_astrological
    )
    
    if not dream_saved:
        raise DatabaseError(f"Failed to save dream for chat_id: {chat_id}")
    
    # Определяем сообщение для пользователя
    save_message = _get_save_confirmation_message(has_astrological)
    
    # Логируем успешное сохранение
    db.log_activity(user, chat_id, "dream_saved_to_diary", f"type:{source_type}, astrological:{has_astrological}")
    
    # Показываем подтверждение
    await query.answer(save_message)
    
    # Убираем кнопки из всех сообщений с толкованием и удаляем сообщение с выбором даты
    await cleanup_interface_after_save(context, chat_id, query.message.text)
    
    # Очищаем временные данные
    db.delete_pending_dream(chat_id)


async def save_dream_to_diary(db, chat_id, pending_dream, source_type, has_astrological):
    """
    Сохраняет сон в дневник
    
    Args:
        db: Database instance
        chat_id: ID чата
        pending_dream: Данные сна
        source_type: Тип источника
        has_astrological: Есть ли астрологическое толкование
    
    Returns:
        bool: True если сон успешно сохранен
    """
    try:
        if has_astrological:
            # Сохраняем ОДИН сон с ОБОИМИ толкованиями
            return db.save_dream(
                chat_id=chat_id,
                dream_text=pending_dream['dream_text'],
                interpretation=pending_dream['interpretation'],  # Обычное толкование
                source_type=source_type,
                astrological_interpretation=pending_dream['astrological_interpretation']  # Астрологическое толкование
            )
        else:
            # Сохраняем сон только с обычным толкованием
            return db.save_dream(
                chat_id=chat_id,
                dream_text=pending_dream['dream_text'],
                interpretation=pending_dream['interpretation'],
                source_type=source_type
            )
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении сна в БД: {e}")
        return False


def _get_save_confirmation_message(has_astrological):
    """
    Возвращает сообщение подтверждения сохранения
    
    Args:
        has_astrological: Есть ли астрологическое толкование
    
    Returns:
        str: Сообщение подтверждения
    """
    if has_astrological:
        return "✅ Сон с обычным и астрологическим толкованием сохранен в дневник!"
    else:
        return "✅ Сон сохранен в дневник!"


async def cleanup_interface_after_save(context, chat_id, current_message_text):
    """
    Очищает интерфейс после сохранения сна
    
    Args:
        context: Telegram context
        chat_id: ID чата
        current_message_text: Текст текущего сообщения
    """
    try:
        # Убираем кнопки из всех сообщений с толкованием и удаляем сообщение с выбором даты
        await cleanup_astrological_interface(context, chat_id, current_message_text)
        logger.info(f"🔍 DEBUG: Интерфейс очищен после сохранения сна")
        
    except Exception as e:
        logger.error(f"🔍 DEBUG: Не удалось очистить интерфейс после сохранения: {e}")
        # Не критичная ошибка, продолжаем работу
