"""
Конфигурация для webhook версии бота
"""
import os
import secrets

# Генерация секретного токена для webhook (если не установлен)
def generate_secret_token():
    """Генерирует случайный секретный токен для webhook"""
    return secrets.token_urlsafe(32)

# Переменные окружения для webhook
WEBHOOK_CONFIG = {
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN"),
    "WEBHOOK_URL": os.getenv("WEBHOOK_URL"),  # https://your-app.railway.app
    "SECRET_TOKEN": os.getenv("SECRET_TOKEN") or generate_secret_token(),
    "PORT": int(os.getenv("PORT", 8000)),
}

def validate_webhook_config():
    """Проверяет корректность конфигурации webhook"""
    required_vars = ["TELEGRAM_TOKEN"]
    missing_vars = [var for var in required_vars if not WEBHOOK_CONFIG[var]]
    
    if missing_vars:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {missing_vars}")
    
    if not WEBHOOK_CONFIG["WEBHOOK_URL"]:
        print("⚠️ WEBHOOK_URL не установлен - webhook не будет настроен автоматически")
    
    return True

def get_webhook_url():
    """Возвращает полный URL для webhook"""
    base_url = WEBHOOK_CONFIG["WEBHOOK_URL"]
    if base_url:
        return f"{base_url.rstrip('/')}/webhook"
    return None

def print_config_status():
    """Выводит статус конфигурации"""
    print("📋 Конфигурация webhook:")
    print(f"  🤖 Bot Token: {'✅ Установлен' if WEBHOOK_CONFIG['TELEGRAM_TOKEN'] else '❌ Отсутствует'}")
    print(f"  🌐 Webhook URL: {WEBHOOK_CONFIG['WEBHOOK_URL'] or '❌ Не установлен'}")
    print(f"  🔐 Secret Token: {'✅ Установлен' if WEBHOOK_CONFIG['SECRET_TOKEN'] else '❌ Отсутствует'}")
    print(f"  🚪 Port: {WEBHOOK_CONFIG['PORT']}")

if __name__ == "__main__":
    validate_webhook_config()
    print_config_status()
