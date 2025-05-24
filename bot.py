from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import openai
import os

TELEGRAM_TOKEN = os.environ["7890202093:AAHEMHem83hLI5Htpabi06EeGncE0iWEZwI"]
OPENAI_API_KEY = os.environ["REMOVED_API_KEYuxL1Fn7FKxXsAS8kTJ9r2TCEKLKkjQIVSCzUvEZyR1wHBo4OVTW0wIwIjt4ljLUJ3T3BlbkFJJOm2NeZ8gbSn0QzAI9gQNv8ONdm13z2YS8yIN1cdZK0XlaWJOdC2QoiVzmrNlNAKndehx3RpIA
"]

openai.api_key = OPENAI_API_KEY

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_message}]
        )
        reply = response.choices[0].message["content"]
    except Exception as e:
        reply = f"Ошибка: {e}"
    await update.message.reply_text(reply)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
