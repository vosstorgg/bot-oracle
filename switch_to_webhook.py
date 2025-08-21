#!/usr/bin/env python3
"""
Скрипт для переключения проекта на webhook архитектуру
"""
import os
import shutil
import sys

def switch_to_webhook():
    """Переключает проект на webhook версию"""
    
    print("🔄 Переключение на webhook архитектуру...")
    
    # Проверяем наличие файлов
    required_files = ['app.py', 'bot_handlers.py', 'Procfile.webhook']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {missing_files}")
        return False
    
    try:
        # Делаем бэкап оригинального Procfile
        if os.path.exists('Procfile'):
            print("📦 Создаем бэкап Procfile...")
            shutil.copy('Procfile', 'Procfile.backup')
        
        # Переключаем Procfile
        print("🔧 Переключаем Procfile на webhook версию...")
        shutil.copy('Procfile.webhook', 'Procfile')
        
        print("✅ Переключение завершено!")
        print("\n📋 Следующие шаги для Railway:")
        print("1. Установите переменную WEBHOOK_URL в Railway")
        print("2. Установите переменную SECRET_TOKEN") 
        print("3. Выполните деплой на Railway")
        print("4. Проверьте https://your-app.railway.app/health")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка переключения: {e}")
        return False

def switch_to_polling():
    """Переключает обратно на polling версию"""
    
    print("🔄 Переключение на polling архитектуру...")
    
    try:
        # Восстанавливаем оригинальный Procfile
        if os.path.exists('Procfile.backup'):
            print("📦 Восстанавливаем оригинальный Procfile...")
            shutil.copy('Procfile.backup', 'Procfile')
        else:
            # Создаем стандартный polling Procfile
            with open('Procfile', 'w') as f:
                f.write('web: python bot.py\n')
        
        print("✅ Переключение на polling завершено!")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка переключения: {e}")
        return False

def show_current_mode():
    """Показывает текущий режим работы"""
    
    if not os.path.exists('Procfile'):
        print("❓ Procfile не найден")
        return
    
    with open('Procfile', 'r') as f:
        content = f.read().strip()
    
    if 'app.py' in content or 'uvicorn' in content:
        print("🌐 Текущий режим: WEBHOOK")
    elif 'bot.py' in content:
        print("📡 Текущий режим: POLLING")
    else:
        print("❓ Неизвестный режим")
    
    print(f"📄 Содержимое Procfile: {content}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("🤖 Управление архитектурой Dream Analysis Bot")
        print("\nИспользование:")
        print("  python switch_to_webhook.py webhook  # Переключить на webhook")
        print("  python switch_to_webhook.py polling  # Переключить на polling")
        print("  python switch_to_webhook.py status   # Показать текущий режим")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "webhook":
        switch_to_webhook()
    elif command == "polling":
        switch_to_polling()
    elif command == "status":
        show_current_mode()
    else:
        print("❌ Неизвестная команда. Используйте: webhook, polling, или status")
