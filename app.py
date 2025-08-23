"""
Главное приложение FastAPI для Dream Analysis Bot
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Импорты обработчиков
from handlers.user import handle_message, handle_voice_message
from handlers.profile import start_command, handle_profile_callbacks, handle_info_callbacks, send_start_menu
from handlers.admin import admin_panel_command, cancel_command, handle_admin_callbacks, handle_admin_broadcast_content, admin_broadcast_states
from handlers.diary import handle_diary_callbacks
from handlers.astrological import (
    handle_astrological_callback, 
    handle_astrological_date_callback, 
    handle_cancel_date_input,
    handle_date_input
)
from handlers.dream_save import handle_save_dream_callback

# Импорты конфигурации
from core.config import TELEGRAM_TOKEN, SECRET_TOKEN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-app.railway.app/webhook
PORT = int(os.getenv("PORT", 8000))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")

# Создаем Telegram Application
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()


async def main_button_handler(update, context):
    """Главный обработчик callback'ов"""
    query = update.callback_query
    await query.answer()
    
    # Логируем нажатие кнопки
    from core.database import db
    db.log_activity(update.effective_user, str(update.effective_chat.id), f"button:{query.data}")
    
    # Обработка главного меню
    if query.data == "main_menu":
        try:
            await query.delete_message()
        except Exception:
            pass
        await send_start_menu(query.message.chat_id, context, update.effective_user)
        return
    
    # Обработчики профиля и информации
    if query.data in ["start_profile", "profile_step:gender", "profile_step:skip", "about", "donate", "start_first_dream"] or \
       query.data.startswith(("gender:", "age:", "lucid:")):
        if query.data in ["about", "donate", "start_first_dream"]:
            await handle_info_callbacks(update, context, query.data)
        else:
            await handle_profile_callbacks(update, context, query.data)
        return
    
    # Обработчики дневника снов
    if query.data.startswith(("diary_page:", "dream_view:", "dream_delete")):
        await handle_diary_callbacks(update, context, query.data)
        return
    
    # Обработчик сохранения сна в дневник
    if query.data.startswith("save_dream:"):
        await handle_save_dream_callback(update, context, query.data)
        return
    
    # Обработчик астрологического толкования
    if query.data.startswith("astrological:"):
        await handle_astrological_callback(update, context, query.data)
        return
    
    # Обработчик выбора даты для астрологического толкования
    if query.data.startswith("astrological_date:"):
        await handle_astrological_date_callback(update, context, query.data)
        return
    
    # Обработчик отмены ввода даты
    if query.data == "cancel_date_input":
        await handle_cancel_date_input(update, context)
        return
    
    # Обработчики админки
    if query.data.startswith(("admin_", "broadcast_confirm")):
        await handle_admin_callbacks(update, context, query.data)
        return


async def main_message_handler(update, context):
    """Главный обработчик сообщений"""
    chat_id = str(update.effective_chat.id)
    
    # Приоритет админским состояниям
    if chat_id in admin_broadcast_states:
        await handle_admin_broadcast_content(update, context)
        return
    
    # Проверяем, ожидается ли ввод даты для астрологического толкования
    if context.user_data.get('waiting_for_date'):
        await handle_date_input(update, context)
        return
    
    # Обработка голосовых сообщений
    if update.message.voice:
        await handle_voice_message(update, context)
        return
    
    # Обработка остальных сообщений
    await handle_message(update, context)


# Добавляем обработчики в приложение
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CommandHandler("admin", admin_panel_command))
telegram_app.add_handler(CommandHandler("cancel", cancel_command))
telegram_app.add_handler(CallbackQueryHandler(main_button_handler))

# Обработчики для всех типов сообщений
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.PHOTO, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.VIDEO, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.Document.ALL, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.AUDIO, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.VOICE, main_message_handler))
telegram_app.add_handler(MessageHandler(filters.Sticker.ALL, main_message_handler))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("🚀 Starting webhook server...")
    
    try:
        # Очищаем Telegram-меню (≡)
        await telegram_app.bot.set_my_commands([])
        logger.info("✅ Telegram menu cleared")
        
        # Настраиваем webhook если URL задан
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
            await telegram_app.bot.set_webhook(
                url=webhook_url,
                secret_token=SECRET_TOKEN,
                drop_pending_updates=True
            )
            logger.info(f"✅ Webhook set to: {webhook_url}")
        else:
            logger.warning("⚠️ WEBHOOK_URL not set - webhook not configured")
        
        # Инициализация Telegram приложения  
        await telegram_app.initialize()
        await telegram_app.start()
        logger.info("✅ Telegram application started")
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise
    
    yield  # Приложение работает
    
    # Shutdown
    logger.info("🛑 Shutting down...")
    try:
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("✅ Telegram application stopped")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")


# Создаем FastAPI приложение
app = FastAPI(
    title="Dream Analysis Bot",
    description="Telegram bot for dream interpretation using Jung's methodology",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Dream Analysis Bot is running",
        "version": "2.0.0",
        "status": "active"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    try:
        # Проверяем, что Telegram приложение работает
        bot_info = await telegram_app.bot.get_me()
        return {
            "status": "healthy",
            "bot_username": bot_info.username,
            "bot_id": bot_info.id,
            "webhook_configured": bool(WEBHOOK_URL)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.post("/webhook")
async def webhook(request: Request):
    """Webhook эндпоинт для получения обновлений от Telegram"""
    try:
        # Проверяем секретный токен если он установлен
        if SECRET_TOKEN:
            token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if token != SECRET_TOKEN:
                logger.warning("Invalid secret token in webhook request")
                raise HTTPException(status_code=403, detail="Invalid secret token")
        
        # Получаем и обрабатываем обновление
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        
        # Добавляем обновление в очередь
        await telegram_app.update_queue.put(update)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
