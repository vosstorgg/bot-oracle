"""
Конфигурация и константы для Dream Analysis Bot
"""
import os
from telegram import ReplyKeyboardMarkup

# === API КОНФИГУРАЦИЯ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "default_secret")

# === DATABASE КОНФИГУРАЦИЯ ===
DATABASE_CONFIG = {
    "host": os.getenv("PGHOST"),
    "port": os.getenv("PGPORT"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
    "dbname": os.getenv("PGDATABASE")
}

# === AI МОДЕЛЬ НАСТРОЙКИ ===
AI_SETTINGS = {
    "model": "gpt-4o",
    "temperature": 0.45,
    "max_tokens": 1400,
    "max_history": 10
}

# === ПУТИ К ФАЙЛАМ ===
STATIC_DIR = "static"
IMAGE_PATHS = {
    "intro": f"{STATIC_DIR}/intro.png",
    "about": f"{STATIC_DIR}/about.png", 
    "donate": f"{STATIC_DIR}/donate.png",
    "quiz": f"{STATIC_DIR}/quiz.png",
    "diary": f"{STATIC_DIR}/diary.png"
}

# === ПРОМПТ ДЛЯ AI ===
DEFAULT_SYSTEM_PROMPT = """You are a qualified dream analyst trained in the methodology of C.G. Jung, with deep knowledge of astrology and esotericism, working within the Western psychological tradition. You interpret dreams as unique messages from the unconscious, drawing on archetypes, symbols, and the collective unconscious. You may reference mythology, astrology, or esoteric concepts metaphorically, if they enrich meaning and maintain internal coherence. Use simple, clear, human language. Avoid quotation marks for symbols and refrain from using specialized terminology. Your task is to identify key images, archetypes, and symbols, and explain their significance for inner development. You do not predict the future, give advice, or act as a therapist. Interpretations must be hypothetical, respectful, and free from rigid or generic meanings. If the user provides the date and location of the dream and requests it, include metaphorical astrological context (e.g. Moon phase, the current planetary positions). If the dream is brief, you may ask 1–3 clarifying questions. If the user declines, interpret only what is available. Maintain a supportive and respectful tone. Match the user's style—concise or detailed, light or deep. Never use obscene language, even if requested; replace it with appropriate, standard synonyms. Do not engage in unrelated topics—gently guide the conversation back to dream analysis. Use only Telegram Markdown formatting (e.g. *bold*, _italic_, `code`) and emojis to illustrate symbols (e.g. 🌑, 👁, 🪞). Do not use HTML.

# Classification
At the start of your response, use one of these emoji classification markers:
🌙 - If the user is describing a dream (their primary intent is dream interpretation)
❓ - If the user is asking clarifying questions or seeking more details about a previous interpretation  
💭 - If the user is having general conversation or the content is not clearly dream-related

# Reply handling
When a user replies to your previous message with a question or clarification:
- Focus ONLY on answering their specific question
- Reference the previous interpretation briefly if needed
- Do NOT re-analyze the entire dream
- Keep your response concise and targeted
- Use ❓ emoji at the start for clarification responses

# User context
Use a paragraph of text to suggest the dream's emotional tone. Try to end your analysis by inviting the user to reflect or respond. Speak Russian using informal 'ты' form with users."""

# === TELEGRAM МЕНЮ ===
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        ["🌙 Разобрать мой сон"],
        ["📖 Дневник снов", "💬 Подписаться на канал автора"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# === ADMIN КОНФИГУРАЦИЯ ===
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
if not ADMIN_CHAT_ID:
    print("⚠️ ВНИМАНИЕ: ADMIN_CHAT_ID не установлен в переменных окружения!")
    print("⚠️ Админские функции будут недоступны!")

ADMIN_CHAT_IDS = [ADMIN_CHAT_ID] if ADMIN_CHAT_ID else []

# === WHISPER НАСТРОЙКИ ===
WHISPER_SETTINGS = {
    "min_duration": 1,  # Уменьшаем минимальную длительность с 2 до 1 секунды
    "max_duration_for_phrase_filter": 3,  # Уменьшаем с 5 до 3 секунд для более мягкой фильтрации
    "suspicious_phrases": [
        # YouTube/видео артефакты (оставляем только самые явные)
        "редактор субтитров", "подписывайтесь на канал", "ставьте лайки", "всем пока",
        "спасибо за просмотр", "до свидания", "увидимся", "пока пока",
        
        # Музыкальные артефакты (убираем общие слова)
        "♪", "♫", "♬", "бит", "бас", "мелодия",
        
        # Технические тесты (оставляем только явные)
        "проверка связи", "тестирование", "один два три",
        
        # Междометия (убираем естественные для речи)
        "эм", "ммм", "хмм", "ага", "угу", "да да", "нет нет",
        "ой", "ах", "ох", "эх", "ух", "блин",
        
        # Новости и медиа (убираем общие слова)
        "новости", "сводка", "прогноз", "погода", "курс валют",
        "последние новости", "в эфире", "передача",
        
        # Имена и бренды (оставляем только явные)
        "субтитры", "ютуб", "youtube", "telegram", "whatsapp",
        "вконтакте", "фейсбук", "инстаграм", "тикток",
        
        # Соцсети и мессенджеры (оставляем только явные)
        "лайк", "репост", "шэр", "subscribe", "follow",
        "комментарий", "сториз", "селфи"
    ]
}

# === ПАГИНАЦИЯ ===
PAGINATION = {
    "dreams_per_page": 10,
    "max_message_length": 4000
}

# === ССЫЛКИ ===
LINKS = {
    "author_channel": "https://t.me/N_W_passage", 
    "donation": "https://pay.cloudtips.ru/p/4f1dd4bf"
}
