import os
import asyncio
import logging
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot_handlers import start_command, button_handler, handle_message, admin_command, admin_broadcast_callback, cancel_command, handle_voice_message

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-app.railway.app/webhook
SECRET_TOKEN = os.getenv("SECRET_TOKEN")  # Секретный токен для безопасности
PORT = int(os.getenv("PORT", 8000))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is required")

# Создаем Telegram Application
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# Добавляем обработчики  
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CommandHandler("admin", admin_command))
telegram_app.add_handler(CommandHandler("cancel", cancel_command))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
# Обработчики для всех типов сообщений (включая медиа)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_message))
telegram_app.add_handler(MessageHandler(filters.VIDEO, handle_message))
telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
telegram_app.add_handler(MessageHandler(filters.AUDIO, handle_message))
telegram_app.add_handler(MessageHandler(filters.VOICE, handle_message))
telegram_app.add_handler(MessageHandler(filters.Sticker.ALL, handle_message))

from contextlib import asynccontextmanager
from telegram import BotCommand

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("🚀 Starting webhook server...")
    
    # Инициализируем Telegram Application
    await telegram_app.initialize()
    await telegram_app.start()
    
    # Очищаем все команды из меню бота (используем только inline кнопки)
    await telegram_app.bot.set_my_commands([])
    logger.info("✅ Меню команд очищено - используются только inline кнопки")
    
    # Настройка webhook (если указан URL)
    if WEBHOOK_URL:
        try:
            webhook_url = f"{WEBHOOK_URL}/webhook"
            await telegram_app.bot.set_webhook(
                url=webhook_url,
                secret_token=SECRET_TOKEN,
                drop_pending_updates=True  # Очищаем очередь при запуске
            )
            logger.info(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}")
    else:
        logger.warning("⚠️ WEBHOOK_URL не установлен - webhook не настроен")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down webhook server...")
    await telegram_app.stop()
    await telegram_app.shutdown()

# Создаем FastAPI приложение
app = FastAPI(title="Dream Analysis Bot", version="2.0", lifespan=lifespan)

@app.get("/")
async def root():
    """Базовый endpoint для проверки здоровья сервера"""
    return {
        "status": "running",
        "service": "Dream Analysis Bot",
        "version": "2.0",
        "webhook": bool(WEBHOOK_URL)
    }

@app.get("/health")
async def health_check():
    """Health check endpoint для Railway"""
    try:
        bot_info = await telegram_app.bot.get_me()
        return {
            "status": "healthy",
            "bot_username": bot_info.username,
            "webhook_configured": bool(WEBHOOK_URL)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Bot not available")

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Основной webhook endpoint для получения обновлений от Telegram"""
    
    # Проверяем секретный токен если он установлен
    if SECRET_TOKEN:
        received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if received_token != SECRET_TOKEN:
            logger.warning("❌ Неверный секретный токен")
            raise HTTPException(status_code=403, detail="Forbidden")
    
    try:
        # Получаем JSON данные
        update_data = await request.json()
        
        # Создаем Update объект
        update = Update.de_json(update_data, telegram_app.bot)
        
        if update:
            # Обрабатываем обновление асинхронно
            asyncio.create_task(telegram_app.process_update(update))
            logger.info(f"📨 Обработано обновление: {update.update_id}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/set_webhook")
async def set_webhook_endpoint():
    """Endpoint для установки webhook (для отладки)"""
    if not WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="WEBHOOK_URL not configured")
    
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            secret_token=SECRET_TOKEN,
            drop_pending_updates=True
        )
        return {"status": "success", "webhook_url": webhook_url}
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/webhook")
async def delete_webhook():
    """Endpoint для удаления webhook (для отладки)"""
    try:
        await telegram_app.bot.delete_webhook(drop_pending_updates=True)
        return {"status": "success", "message": "Webhook deleted"}
    except Exception as e:
        logger.error(f"❌ Ошибка удаления webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/webhook_info")
async def webhook_info():
    """Получить информацию о текущем webhook"""
    try:
        webhook_info = await telegram_app.bot.get_webhook_info()
        return {
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message,
            "max_connections": webhook_info.max_connections,
            "allowed_updates": webhook_info.allowed_updates
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Запуск сервера (для локальной разработки)
if __name__ == "__main__":
    import uvicorn
    logger.info(f"🌟 Запуск сервера на порту {PORT}")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        reload=False  # Отключаем reload в продакшене
    )
