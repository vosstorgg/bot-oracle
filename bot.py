import os
import openai
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 🔐 API ключи
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🧠 Настройки истории
MAX_HISTORY = 1000  # Кол-во последних сообщений на каждый запрос

# 🗃 Подключение к PostgreSQL
conn = psycopg2.connect(
    host=os.environ["PGHOST"],
    port=os.environ["PGPORT"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
    database=os.environ["PGDATABASE"]
)
conn.autocommit = True

# 🔧 Инициализация таблицы
with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        );
    """)

# Таблица статистики пользователей
with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            chat_id TEXT PRIMARY KEY,
            messages_sent INTEGER DEFAULT 0,
            symbols_sent INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)

# 📥 Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_message = update.message.text

    # Сохраняем сообщение пользователя
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "user", user_message, datetime.utcnow())
        
# Обновляем статистику пользователя
with conn.cursor() as cur:
    cur.execute("""
        INSERT INTO user_stats (chat_id, messages_sent, symbols_sent)
        VALUES (%s, 1, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET
            messages_sent = user_stats.messages_sent + 1,
            symbols_sent = user_stats.symbols_sent + EXCLUDED.symbols_sent,
            updated_at = NOW()
    """, (chat_id, len(user_message)))

    # Загружаем последние MAX_HISTORY сообщений
    with conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE chat_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (chat_id, MAX_HISTORY * 2))  # умножаем на 2 — пары user+assistant

        rows = cur.fetchall()
        history = [{"role": role, "content": content} for role, content in reversed(rows)]

    )
    
    # Отправляем в OpenAI
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=history + [
                {
                    "role": "system",
                    "content": "Пожалуйста, не превышай 3000 символов в своём ответе. Отвечай кратко и по существу, избегай лишних подробностей."
                }
            ],
            max_tokens=1000  # ~3000–3500 символов
        )
        reply = response.choices[0].message.content

    except Exception as e:
        reply = f"Ошибка OpenAI: {e}"


        # ✂️ Ограничение длины
        MAX_REPLY_LENGTH = 3000
        if len(reply) > MAX_REPLY_LENGTH:
            reply = reply[:MAX_REPLY_LENGTH] + "\n\n… (ответ обрезан)"

    except Exception as e:
        reply = f"Ошибка OpenAI: {e}"

    # Сохраняем ответ
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
            (chat_id, "assistant", reply, datetime.utcnow())
        )

    await update.message.reply_text(reply)

# 🚀 Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
