# Dream Analysis Bot

Telegram бот для анализа снов с использованием методологии К.Г. Юнга и OpenAI GPT-4.

## 🚀 Возможности

- 🌙 Анализ снов через текстовые и голосовые сообщения
- 🎤 Распознавание речи через OpenAI Whisper
- 📖 Дневник снов с автоматическим сохранением
- 👤 Персонализированные профили пользователей
- 🔧 Админ панель и массовые рассылки
- 🌐 Webhook архитектура для продакшена

## 🏗️ Архитектура

```
📁 bot-oracle/
├── 🚀 app.py                    # FastAPI main app
├── 📁 core/                     # Бизнес-логика
│   ├── config.py                # Конфигурация
│   ├── database.py              # Операции с БД
│   ├── ai_service.py            # OpenAI интеграция
│   └── models.py                # Модели данных
├── 📁 handlers/                 # Telegram обработчики
│   ├── user.py                  # Пользователи и сны
│   ├── profile.py               # Профили и онбординг
│   ├── diary.py                 # Дневник снов
│   └── admin.py                 # Админ панель
└── 📁 static/                   # Изображения
```

## 🛠️ Развертывание на Railway

### 1. Переменные окружения

Настройте в Railway UI следующие переменные:

```bash
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration (PostgreSQL)
PGHOST=your_postgres_host
PGPORT=5432
PGUSER=your_postgres_user
PGPASSWORD=your_postgres_password
PGDATABASE=your_postgres_database

# Webhook Configuration
WEBHOOK_URL=https://your-app.railway.app
SECRET_TOKEN=your_secret_token_here

# Application Configuration
PORT=8000
```

### 2. Настройка PostgreSQL

Railway автоматически создаст PostgreSQL базу данных. Используйте переменные окружения которые Railway предоставляет.

### 3. Деплой

1. Подключите GitHub репозиторий к Railway
2. Railway автоматически определит Python проект
3. Настройте переменные окружения
4. Деплой произойдет автоматически

### 4. Проверка

- Healthcheck: `https://your-app.railway.app/health`
- Webhook endpoint: `https://your-app.railway.app/webhook`

## 🔧 Локальная разработка

```bash
# Клонирование
git clone https://github.com/vosstorgg/bot-oracle.git
cd bot-oracle

# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env файл

# Запуск
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## 📋 Требования

- Python 3.9+
- PostgreSQL
- Telegram Bot Token
- OpenAI API Key

## 🎯 Основные зависимости

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `python-telegram-bot` - Telegram Bot API
- `openai` - OpenAI API (GPT-4, Whisper)
- `psycopg2-binary` - PostgreSQL adapter

## 📝 API Endpoints

- `GET /` - Корневой endpoint
- `GET /health` - Healthcheck
- `POST /webhook` - Telegram webhook

## 🔒 Безопасность

- Секретный токен для webhook
- Валидация всех входящих запросов
- Защищенная админ панель
- Логирование всех действий

## 📖 Лицензия

MIT License
