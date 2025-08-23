"""
Обработчики для астрологического толкования снов
"""
import logging
from datetime import datetime, timezone, timedelta
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from core.utils import cleanup_astrological_interface, log_error_and_notify

logger = logging.getLogger(__name__)


async def handle_astrological_callback(update, context, callback_data):
    """Обработчик кнопки 'Астрологическое толкование'"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Получаем данные сна из временного хранилища в БД
        from core.database import db
        pending_dream = db.get_pending_dream(chat_id)
        if not pending_dream:
            await query.answer("❌ Данные сна не найдены. Попробуйте еще раз.")
            return
        
        # Извлекаем source_type из callback_data
        source_type = callback_data.split(":")[1]
        logger.info(f"🔍 DEBUG: handle_astrological_callback - callback_data = {callback_data}, source_type = {source_type}")
        
        # Показываем уточнение даты
        await query.answer("🔮 Уточняю дату сна...")
        
        # Отправляем сообщение с выбором даты
        date_msg = await query.message.reply_text(
            "Когда тебе приснился этот сон?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Сегодня", callback_data=f"astrological_date:today:{source_type}")],
                [InlineKeyboardButton("Вчера", callback_data=f"astrological_date:yesterday:{source_type}")],
                [InlineKeyboardButton("Ввести дату", callback_data=f"astrological_date:custom:{source_type}")]
            ])
        )
        
        # Сохраняем сообщение с кнопками дат для последующего редактирования
        context.user_data['date_selection_msg'] = date_msg
        
    except Exception as e:
        await query.answer("❌ Произошла ошибка при выборе даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_date_error", str(e))


async def handle_astrological_date_callback(update, context, callback_data):
    """Обработчик выбора даты для астрологического толкования"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Парсим callback_data: astrological_date:date_type:source_type
        parts = callback_data.split(":")
        date_type = parts[1]
        source_type = parts[2]
        
        # Получаем данные сна из временного хранилища в БД
        from core.database import db
        pending_dream = db.get_pending_dream(chat_id)
        if not pending_dream:
            await query.answer("❌ Данные сна не найдены. Попробуйте еще раз.")
            return
        
        # Определяем дату в зависимости от выбора
        today = datetime.now(timezone.utc)
        
        if date_type == "today":
            selected_date = today
            date_str = today.strftime("%Y-%m-%d")
        elif date_type == "yesterday":
            selected_date = today - timedelta(days=1)
            date_str = selected_date.strftime("%Y-%m-%d")
        elif date_type == "custom":
            # Запрашиваем ввод даты
            await query.answer("Введи дату в формате ДД.ММ.ГГГГ")
            
            # Устанавливаем состояние ожидания даты
            context.user_data['waiting_for_date'] = True
            context.user_data['pending_astrological'] = {
                'source_type': source_type,
                'pending_dream': pending_dream
            }
            
            # Редактируем сообщение с инструкцией
            await query.message.edit_text(
                "Введи дату в формате ДД.ММ.ГГГГ\n\nНапример: 15.01.2024",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Отмена", callback_data="cancel_date_input")]
                ])
            )
            return
        else:
            await query.answer("❌ Неизвестный тип даты.")
            return
        
        # Запускаем астрологический анализ с выбранной датой
        await perform_astrological_analysis(update, context, pending_dream, source_type, date_str)
        
    except Exception as e:
        await query.answer("❌ Произошла ошибка при выборе даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_date_error", str(e))


async def perform_astrological_analysis(update, context, pending_dream, source_type, date_str):
    """Выполнение астрологического анализа с указанной датой"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Показываем "размышляет"
        await query.answer("🔮 Анализирую сон астрологически...")
        
        # Отправляем сообщение о начале астрологического анализа
        thinking_msg = await query.message.reply_text("🔮 Размышляю над астрологическим значением твоего сна...")
        
        # Получаем астрологическое толкование с датой
        from core.ai_service import ai_service
        astrological_reply = await ai_service.analyze_dream_astrologically(
            pending_dream['dream_text'], 
            pending_dream['interpretation'],
            source_type,
            date_str
        )
        
        # Логируем астрологическое толкование
        from core.database import db
        db.log_activity(user, chat_id, "astrological_interpretation", f"date:{date_str}, reply:{astrological_reply[:300]}")
        db.save_message(chat_id, "assistant", astrological_reply)
        
        # Определяем тип ответа для создания соответствующей клавиатуры
        message_type = ai_service.extract_message_type(astrological_reply)
        
        if message_type == 'dream':
            # Для астрологических толкований добавляем кнопку "Сохранить в дневник"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Сохранить в дневник снов", callback_data=f"save_dream:{source_type}")]
            ])
            
            # Обновляем временные данные для астрологического толкования
            # Сохраняем ОБА толкования: обычное и астрологическое
            db.update_pending_dream_astrological(chat_id, astrological_reply)
            logger.info(f"🔍 DEBUG: perform_astrological_analysis - обновлен pending_dream в БД")
            
            # Убираем кнопки из обычного толкования и удаляем сообщение с выбором даты
            await cleanup_astrological_interface(context, chat_id, astrological_reply)
                
        else:
            # Для других типов сообщений без кнопок
            keyboard = None
        
        # Отправляем астрологическое толкование
        if keyboard:
            await thinking_msg.edit_text(astrological_reply, parse_mode='Markdown', reply_markup=keyboard)
        else:
            await thinking_msg.edit_text(astrological_reply, parse_mode='Markdown')
        
    except Exception as e:
        await query.answer("❌ Произошла ошибка при астрологическом анализе.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_error", str(e))
        await thinking_msg.edit_text(f"❌ Ошибка при астрологическом анализе: {e}")


async def perform_astrological_analysis_from_date_input(update, context, pending_dream, source_type, date_str):
    """Выполнение астрологического анализа с введенной датой"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    try:
        # Показываем "размышляет"
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        thinking_msg = await update.message.reply_text("🔮 Размышляю над астрологическим значением твоего сна...")
        
        # Получаем астрологическое толкование с датой
        from core.ai_service import ai_service
        astrological_reply = await ai_service.analyze_dream_astrologically(
            pending_dream['dream_text'], 
            pending_dream['interpretation'],
            source_type,
            date_str
        )
        
        # Логируем астрологическое толкование
        from core.database import db
        db.log_activity(user, chat_id, "astrological_interpretation", f"date:{date_str}, reply:{astrological_reply[:300]}")
        db.save_message(chat_id, "assistant", astrological_reply)
        
        # Определяем тип ответа для создания соответствующей клавиатуры
        message_type = ai_service.extract_message_type(astrological_reply)
        
        if message_type == 'dream':
            # Для астрологических толкований добавляем кнопку "Сохранить в дневник"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Сохранить в дневник снов", callback_data=f"save_dream:{source_type}")]
            ])
            
            # Обновляем временные данные для астрологического толкования
            # Сохраняем ОБА толкования: обычное и астрологическое
            db.update_pending_dream_astrological(chat_id, astrological_reply)
            
            # Убираем кнопки из исходного сообщения с толкованием и удаляем сообщение с выбором даты
            await cleanup_astrological_interface(context, chat_id, astrological_reply)
            
        else:
            # Для других типов сообщений без кнопок
            keyboard = None
        
        # Отправляем астрологическое толкование
        if keyboard:
            await thinking_msg.edit_text(astrological_reply, parse_mode='Markdown', reply_markup=keyboard)
        else:
            await thinking_msg.edit_text(astrological_reply, parse_mode='Markdown')
        
    except Exception as e:
        await thinking_msg.edit_text(f"❌ Ошибка при астрологическом анализе: {e}")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_error", str(e))


async def handle_cancel_date_input(update, context):
    """Обработчик отмены ввода даты"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Очищаем состояние ожидания даты
        context.user_data.pop('waiting_for_date', None)
        context.user_data.pop('pending_astrological', None)
        
        # Показываем сообщение об отмене
        await query.answer("❌ Ввод даты отменен")
        
        # Удаляем сообщение с вводом даты
        await query.message.delete()
        
    except Exception as e:
        await query.answer("❌ Ошибка при отмене ввода даты")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "cancel_date_error", str(e))


def is_valid_date_format(date_str):
    """Проверка корректности формата даты ДД.ММ.ГГГГ"""
    try:
        # Проверяем формат
        if not date_str or len(date_str) != 10 or date_str[2] != '.' or date_str[5] != '.':
            return False
        
        # Извлекаем части даты
        day = int(date_str[0:2])
        month = int(date_str[3:5])
        year = int(date_str[6:10])
        
        # Проверяем разумные пределы
        if year < 1900 or year > 2100:
            return False
        if month < 1 or month > 12:
            return False
        if day < 1 or day > 31:
            return False
        
        # Проверяем корректность дней для месяца
        try:
            datetime(year, month, day)
            return True
        except ValueError:
            return False
            
    except (ValueError, IndexError):
        return False


def convert_date_format(date_str):
    """Конвертация даты из ДД.ММ.ГГГГ в YYYY-MM-DD"""
    day = date_str[0:2]
    month = date_str[3:5]
    year = date_str[6:10]
    return f"{year}-{month}-{day}"


async def handle_date_input(update, context):
    """Обработчик ввода даты для астрологического толкования"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    try:
        # Получаем введенную дату
        date_input = update.message.text.strip()
        
        # Валидируем формат даты ДД.ММ.ГГГГ
        if not is_valid_date_format(date_input):
            await update.message.reply_text(
                "❌ Неверный формат даты. Используй формат ДД.ММ.ГГГГ\n\nНапример: 15.01.2024",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Отмена", callback_data="cancel_date_input")]
                ])
            )
            return
        
        # Конвертируем дату в нужный формат
        date_str = convert_date_format(date_input)
        
        # Получаем данные для астрологического анализа
        pending_astrological = context.user_data.get('pending_astrological')
        if not pending_astrological:
            await update.message.reply_text("❌ Данные для астрологического анализа не найдены.")
            return
        
        # Очищаем состояние ожидания даты
        context.user_data.pop('waiting_for_date', None)
        pending_data = context.user_data.pop('pending_astrological')
        
        # Запускаем астрологический анализ с введенной датой
        await perform_astrological_analysis_from_date_input(
            update, context, 
            pending_data['pending_dream'], 
            pending_data['source_type'], 
            date_str
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Произошла ошибка при обработке даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "date_input_error", str(e))
