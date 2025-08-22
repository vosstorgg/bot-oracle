"""
Обработчики для пользовательских взаимодействий (сны, голосовые сообщения)
"""
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from core.database import db
from core.ai_service import ai_service
from core.config import MAIN_MENU, AI_SETTINGS, IMAGE_PATHS


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений пользователей"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Проверяем админские состояния (импортируем здесь, чтобы избежать циклических импортов)
    from handlers.admin import admin_broadcast_states, handle_admin_broadcast_content
    
    # Приоритет админским состояниям
    if chat_id in admin_broadcast_states:
        await handle_admin_broadcast_content(update, context)
        return
    
    # Извлекаем текст сообщения (учитываем caption для медиа)
    user_message = None
    if update.message.text:
        user_message = update.message.text
    elif update.message.caption:
        user_message = update.message.caption
    
    # Обработка кнопок главного меню
    if user_message == "🌙 Разобрать мой сон":
        await start_first_dream_command(update, context)
        return
    
    if user_message == "💬 Подписаться на канал автора":
        await channel_view_command(update, context)
        return
    
    if user_message == "📖 Дневник снов":
        from handlers.diary import show_dream_diary
        await show_dream_diary(update, context)
        return
    
    # Для обычных пользователей - обрабатываем только текстовые описания снов
    if not user_message:
        await update.message.reply_text(
            "🤔 Я анализирую только текстовые описания снов. Расскажи мне свой сон словами или запиши голосовое сообщение, и я помогу его понять.",
            reply_markup=MAIN_MENU
        )
        return
    
    # Логирование и обработка сна
    db.log_activity(user, chat_id, "message", user_message)
    db.log_activity(user, chat_id, "gpt_request", f"model={AI_SETTINGS['model']}, temp={AI_SETTINGS['temperature']}, max_tokens={AI_SETTINGS['max_tokens']}")
    
    # Отправка "размышляет"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    thinking_msg = await update.message.reply_text("〰️ Размышляю...")
    
    # Используем общую функцию для обработки текста сна (source_type = 'text' по умолчанию)
    # Передаем thinking_msg, чтобы "Размышляю..." заменилось на толкование
    await process_dream_text(update, context, user_message, thinking_msg, 'text')


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    voice = update.message.voice
    
    db.log_activity(user, chat_id, "voice_message", f"duration: {voice.duration}s")
    
    # Отправляем сообщение о начале обработки
    processing_msg = await update.message.reply_text("🎤 Получил голосовое сообщение, расшифровываю...")
    
    try:
        # Скачиваем файл
        file = await context.bot.get_file(voice.file_id)
        file_content = await file.download_as_bytearray()
        
        # Транскрибируем через Whisper
        transcribed_text = await ai_service.transcribe_voice(bytes(file_content), "ogg")
        
        if not transcribed_text:
            await processing_msg.edit_text(
                "❌ Не удалось распознать речь. Попробуйте записать сообщение заново или написать текстом."
            )
            return
        
        # Проверяем на подозрительность (галлюцинации Whisper)
        should_reject, rejection_reason = ai_service.should_reject_voice_message(transcribed_text, voice.duration)
        
        # Детальное логирование для диагностики
        db.log_activity(user, chat_id, "voice_analysis", 
                       f"duration: {voice.duration}s, words: {len(transcribed_text.split())}, "
                       f"text: '{transcribed_text[:100]}', should_reject: {should_reject}, reason: {rejection_reason}")
        
        if should_reject:
            db.log_activity(user, chat_id, "voice_rejected", f"reason: {rejection_reason}, text: {transcribed_text}")
            await processing_msg.edit_text(
                "🤔 Не удалось распознать речь. Попробуйте записать сообщение четче или написать текстом."
            )
            return
        
        db.log_activity(user, chat_id, "voice_transcribed", transcribed_text[:100])
        
        try:
            # Показываем полную расшифровку и оставляем её видимой
            await processing_msg.edit_text(
                f"🎤 ➜ 📝 *Расшифровка:* {transcribed_text}",
                parse_mode='Markdown'
            )
            # Отправляем новое сообщение "Размышляю..." для замены на толкование
            thinking_msg = await update.message.reply_text("〰️ Размышляю над твоим сном...")
            # Обрабатываем расшифрованный текст как голосовое сообщение
            await process_dream_text(update, context, transcribed_text, thinking_msg, 'voice')
        except BadRequest:
            # Если не удается редактировать, отправляем новое сообщение и обрабатываем без редактирования
            await update.message.reply_text(
                f"🎤 ➜ 📝 *Расшифровка:* {transcribed_text}",
                parse_mode='Markdown'
            )
            # Отправляем новое сообщение для анализа
            thinking_msg = await update.message.reply_text("〰️ Размышляю над твоим сном...")
            await process_dream_text(update, context, transcribed_text, thinking_msg, 'voice')
        
    except Exception as e:
        db.log_activity(user, chat_id, "voice_error", str(e))
        await processing_msg.edit_text(
            f"❌ Ошибка при обработке голосового сообщения: {e}\n\nПопробуйте отправить текстом."
        )


async def process_dream_text(update: Update, context: ContextTypes.DEFAULT_TYPE, dream_text: str, message_to_edit=None, source_type: str = 'text'):
    """Обработка текста сна через OpenAI (используется для текста и голосовых)"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Обновляем статистику пользователя
    db.update_user_stats(user, chat_id, dream_text)
    
    # Сохраняем сообщение пользователя
    db.save_message(chat_id, "user", dream_text)
    
    # Загружаем историю сообщений
    history = db.get_message_history(chat_id, AI_SETTINGS["max_history"])
    
    # Получаем профиль пользователя
    profile = db.get_user_profile(chat_id)
    profile_info = ai_service.format_profile_info(profile)
    
    try:
        # Анализируем сон через AI
        reply = await ai_service.analyze_dream(dream_text, history, profile_info)
        db.log_activity(user, chat_id, "dream_interpreted", reply[:300])
        
        # Классифицируем ответ и сохраняем сны в дневник
        message_type = ai_service.extract_message_type(reply)
        if message_type == 'dream':
            # Сохраняем сон в дневник с переданным source_type
            dream_saved = db.save_dream(
                chat_id=chat_id, 
                dream_text=dream_text, 
                interpretation=reply,
                source_type=source_type
            )
            
            if dream_saved:
                db.log_activity(user, chat_id, "dream_saved_to_diary", f"type:{source_type}")
            else:
                db.log_activity(user, chat_id, "dream_save_failed", f"type:{source_type}")
    
    except Exception as e:
        reply = f"❌ Ошибка, повторите ещё раз: {e}"
        db.log_activity(user, chat_id, "dream_interpretation_error", str(e))
    
    # Сохраняем ответ ассистента
    db.save_message(chat_id, "assistant", reply)
    
    # Отправляем или редактируем сообщение с результатом
    if message_to_edit:
        try:
            # Редактируем сообщение "Размышляю..." на толкование
            await message_to_edit.edit_text(reply, parse_mode='Markdown', reply_markup=MAIN_MENU)
        except BadRequest:
            # Если не удается редактировать, отправляем новое сообщение
            await update.message.reply_text(reply, parse_mode='Markdown', reply_markup=MAIN_MENU)
    else:
        await update.message.reply_text(reply, parse_mode='Markdown', reply_markup=MAIN_MENU)


async def start_first_dream_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для начала анализа первого сна"""
    await update.message.reply_text(
        "✨ Расскажи мне свой сон, даже если он странный, запутанный или пугающий – так подробно, как можешь. "
        "Опиши атмосферу, эмоции, персонажей и, если хочешь, укажи дату и место сна (можно просто город).",
        reply_markup=MAIN_MENU 
    )


async def channel_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра канала автора"""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from core.config import LINKS
    
    await update.message.reply_text(
        "Лучшая поддержка сейчас — подписаться на канал автора.\n\nСпасибо! ❤️",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подписаться на канал", url=LINKS["author_channel"])]
        ])
    )
