"""
Централизованная обработка ошибок для Dream Analysis Bot
"""
import logging
import traceback
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)


class BotError(Exception):
    """Базовый класс для ошибок бота"""
    def __init__(self, message: str, user_message: str = None):
        self.message = message
        self.user_message = user_message or "❌ Произошла ошибка. Попробуйте еще раз."
        super().__init__(self.message)


class DatabaseError(BotError):
    """Ошибки базы данных"""
    def __init__(self, message: str):
        super().__init__(message, "❌ Ошибка сохранения данных. Попробуйте позже.")


class AIServiceError(BotError):
    """Ошибки AI сервиса"""
    def __init__(self, message: str):
        super().__init__(message, "❌ Ошибка анализа сна. Попробуйте еще раз.")


class ValidationError(BotError):
    """Ошибки валидации данных"""
    def __init__(self, message: str, user_message: str = None):
        super().__init__(message, user_message or "❌ Неверный формат данных.")


def handle_errors(error_type: str = "general"):
    """
    Декоратор для обработки ошибок в функциях обработчиков
    
    Args:
        error_type: Тип ошибки для логирования
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except BotError as e:
                # Обрабатываем наши собственные ошибки
                await _handle_bot_error(e, error_type, *args)
            except Exception as e:
                # Обрабатываем неожиданные ошибки
                await _handle_unexpected_error(e, error_type, *args)
        return wrapper
    return decorator


async def _handle_bot_error(error: BotError, error_type: str, *args):
    """Обработка известных ошибок бота"""
    logger.error(f"{error_type}_error: {error.message}")
    
    # Пытаемся извлечь update и context из аргументов
    update, context = _extract_update_context(args)
    
    if update and update.callback_query:
        await update.callback_query.answer(error.user_message)
    elif update and update.message:
        await update.message.reply_text(error.user_message)
    
    # Логируем в базу данных если возможно
    await _log_to_database(error_type, str(error), update)


async def _handle_unexpected_error(error: Exception, error_type: str, *args):
    """Обработка неожиданных ошибок"""
    error_details = traceback.format_exc()
    logger.error(f"Unexpected {error_type}_error: {error}\n{error_details}")
    
    # Пытаемся извлечь update и context из аргументов
    update, context = _extract_update_context(args)
    
    user_message = "❌ Произошла неожиданная ошибка. Мы уже работаем над исправлением."
    
    if update and update.callback_query:
        await update.callback_query.answer(user_message)
    elif update and update.message:
        await update.message.reply_text(user_message)
    
    # Логируем в базу данных если возможно
    await _log_to_database(f"{error_type}_unexpected", str(error), update)


def _extract_update_context(args):
    """Извлекает update и context из аргументов функции"""
    update = None
    context = None
    
    for arg in args:
        if hasattr(arg, 'effective_user') and hasattr(arg, 'effective_chat'):
            update = arg
        elif hasattr(arg, 'bot') and hasattr(arg, 'user_data'):
            context = arg
    
    return update, context


async def _log_to_database(error_type: str, error_message: str, update):
    """Логирует ошибку в базу данных"""
    try:
        if not update:
            return
            
        from core.database import db
        
        user = update.effective_user
        chat_id = str(update.effective_chat.id)
        
        db.log_activity(user, chat_id, error_type, error_message[:500])  # Ограничиваем длину
        
    except Exception as e:
        logger.error(f"Failed to log error to database: {e}")


def safe_int_conversion(value: str, default: int = 0) -> int:
    """Безопасное преобразование строки в число"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_callback_data_split(callback_data: str, expected_parts: int = 2) -> list:
    """Безопасное разделение callback_data"""
    try:
        parts = callback_data.split(":")
        if len(parts) < expected_parts:
            raise ValidationError(f"Invalid callback_data format: {callback_data}")
        return parts
    except Exception:
        raise ValidationError(f"Failed to parse callback_data: {callback_data}")


async def validate_pending_dream(db, chat_id: str):
    """Валидация существования pending_dream"""
    pending_dream = db.get_pending_dream(chat_id)
    if not pending_dream:
        raise ValidationError(
            f"No pending dream found for chat_id: {chat_id}",
            "❌ Данные сна не найдены. Попробуйте еще раз."
        )
    return pending_dream
