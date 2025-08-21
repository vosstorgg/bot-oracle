# 🔄 Webhook версия Dream Analysis Bot

Этот документ содержит инструкции по переходу с polling на webhook архитектуру.

## 📋 Структура проекта

```
bot-oracle/
├── bot.py              # Оригинальная polling версия (НЕ ТРОГАТЬ в production)
├── app.py              # Новая webhook версия
├── bot_handlers.py     # Общие обработчики для обеих версий
├── webhook_config.py   # Конфигурация webhook
├── requirements.txt    # Обновленные зависимости
├── Procfile           # Для polling версии (production)
├── Procfile.webhook   # Для webhook версии (тесты)
└── README_WEBHOOK.md  # Этот файл
```

## 🚀 Развертывание на Railway

### 1. Тестовое развертывание (ветка main)

1. **Создайте новый сервис на Railway** для тестов
2. **Подключите ветку `main`** этого репозитория
3. **Установите переменные окружения:**
   ```
   TELEGRAM_TOKEN=your_test_bot_token
   WEBHOOK_URL=https://your-test-app.railway.app
   SECRET_TOKEN=any_random_32_char_string
   OPENAI_API_KEY=your_openai_key
   PGHOST=your_postgres_host
   PGPORT=5432
   PGUSER=your_postgres_user
   PGPASSWORD=your_postgres_password
   PGDATABASE=your_postgres_db
   ```

4. **Переименуйте Procfile:**
   ```bash
   mv Procfile Procfile.polling
   mv Procfile.webhook Procfile
   ```

### 2. Быстрый запуск на Railway

Все тестирование проводится сразу на Railway без локальной разработки.

## 🔧 API Endpoints

### Основные endpoints:

- `GET /` - Статус сервера
- `GET /health` - Health check для Railway
- `POST /webhook` - Получение обновлений от Telegram
- `GET /webhook_info` - Информация о текущем webhook

### Отладочные endpoints:

- `POST /set_webhook` - Принудительная установка webhook
- `DELETE /webhook` - Удаление webhook

## 🔐 Безопасность

Webhook использует секретный токен для верификации запросов от Telegram:
- Устанавливается в переменной `SECRET_TOKEN`
- Проверяется в заголовке `X-Telegram-Bot-Api-Secret-Token`
- Автоматически генерируется если не указан

## 📊 Мониторинг

### Логи
Все события логируются с метками:
- `📨` - Обработка обновлений
- `✅` - Успешные операции  
- `❌` - Ошибки
- `⚠️` - Предупреждения

### Health Check
```bash
curl https://your-app.railway.app/health
```

### Webhook Status
```bash
curl https://your-app.railway.app/webhook_info
```

## 🔄 Переход на production

1. **Протестируйте все функции** в тестовой среде
2. **Убедитесь в стабильности** webhook версии
3. **В production ветке:**
   - Замените `bot.py` на `app.py`
   - Обновите `Procfile`
   - Обновите `requirements.txt`
4. **Переключите webhook** основного бота

## 🚨 Rollback план

Если что-то пойдет не так:
1. Откатите изменения в production ветке
2. Удалите webhook: `curl -X DELETE https://your-app.railway.app/webhook`
3. Восстановите polling в оригинальном `bot.py`

## 🔧 Troubleshooting на Railway

### Webhook не получает обновления
1. Проверьте URL в Railway logs или `/webhook_info`
2. Убедитесь что WEBHOOK_URL указан корректно
3. Проверьте SECRET_TOKEN в переменных окружения

### Railway показывает ошибку
1. Проверьте логи: Railway dashboard → Deployments → Logs
2. Убедитесь что все переменные окружения установлены
3. Проверьте health check: `https://your-app.railway.app/health`

### Бот не отвечает
1. Проверьте подключение к PostgreSQL в логах
2. Убедитесь что OpenAI API ключ работает
3. Проверьте webhook статус: `https://your-app.railway.app/webhook_info`

## 📈 Преимущества webhook

- ⚡ Мгновенная доставка сообщений (vs 1-2 сек задержка polling)
- 💰 Экономия ресурсов (нет постоянных HTTP запросов)
- 🔒 Повышенная безопасность (секретный токен)
- 📈 Лучшая масштабируемость
