"""
Обработчики для сохранения снов в дневник
"""
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from core.utils import cleanup_astrological_interface, cleanup_astrological_interface_by_ids, remove_message_buttons_by_id
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
    
    # Обновляем статистику сохраненных снов
    db.increment_dreams_saved(user, chat_id)
    
    # Показываем подтверждение
    await query.answer(save_message)
    
    # Убираем кнопки - логика зависит от наличия астрологического толкования
    await cleanup_interface_after_save(context, chat_id, query.message.text, query.message.message_id, has_astrological)
    
    # Очищаем временные данные только если есть астрологическое толкование
    # Если нет - оставляем pending_dream для возможного создания астрологического толкования
    if has_astrological:
        db.delete_pending_dream(chat_id)
        logger.info(f"🔍 DEBUG: Удален pending_dream после сохранения с астрологическим толкованием")


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


async def cleanup_interface_after_save(context, chat_id, current_message_text, current_message_id, has_astrological):
    """
    Очищает интерфейс после сохранения сна
    
    Args:
        context: Telegram context
        chat_id: ID чата
        current_message_text: Текст текущего сообщения
        current_message_id: ID текущего сообщения
        has_astrological: Есть ли астрологическое толкование
    """
    try:
        if has_astrological:
            # Если есть астрологическое толкование - убираем кнопки из ВСЕХ сообщений
            logger.info(f"🔍 DEBUG: Есть астрологическое толкование - убираем все кнопки")
            
            # Убираем кнопки из текущего сообщения (астрологическое толкование)
            await remove_message_buttons_by_id(context, chat_id, current_message_id)
            
            # Получаем ID других сообщений из context для очистки
            dream_interpretation_msg_id = context.user_data.get('dream_interpretation_msg_id')
            date_message_id = context.user_data.get('date_selection_msg_id')
            
            if dream_interpretation_msg_id or date_message_id:
                # Используем надежный метод с ID сообщений
                await cleanup_astrological_interface_by_ids(context, chat_id, dream_interpretation_msg_id, date_message_id)
            else:
                # Fallback к старому методу
                await cleanup_astrological_interface(context, chat_id, current_message_text)
            
            # Очищаем сохраненные ID из context
            context.user_data.pop('dream_interpretation_msg_id', None)
            context.user_data.pop('date_selection_msg_id', None)
            context.user_data.pop('original_message_id', None)
            
        else:
            # Если НЕТ астрологического толкования - убираем только кнопку "Сохранить" из исходного сообщения
            logger.info(f"🔍 DEBUG: Нет астрологического толкования - убираем только кнопку сохранения")
            
            # Заменяем кнопки в исходном сообщении, оставляя только кнопку "Астрологическое толкование"
            dream_interpretation_msg_id = context.user_data.get('dream_interpretation_msg_id')
            
            if dream_interpretation_msg_id:
                # Создаем новую клавиатуру только с кнопкой астрологического толкования
                from core.database import db
                
                # Получаем source_type из pending_dream для создания правильного callback_data
                pending_dream = db.get_pending_dream(chat_id)
                if pending_dream:
                    source_type = pending_dream.get('source_type', 'text')
                    new_keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔮 Астрологическое толкование", callback_data=f"astrological:{source_type}")]
                    ])
                    
                    try:
                        await context.bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=dream_interpretation_msg_id,
                            reply_markup=new_keyboard
                        )
                        logger.info(f"🔍 DEBUG: Заменили кнопки в сообщении {dream_interpretation_msg_id}")
                    except Exception as e:
                        logger.warning(f"🔍 DEBUG: Не удалось заменить кнопки в исходном сообщении: {e}")
            
            # НЕ очищаем dream_interpretation_msg_id, так как кнопка астрологического толкования остается активной
        
        logger.info(f"🔍 DEBUG: Интерфейс очищен после сохранения сна (astrological: {has_astrological})")
        
    except Exception as e:
        logger.error(f"🔍 DEBUG: Не удалось очистить интерфейс после сохранения: {e}")
        # Не критичная ошибка, продолжаем работу
