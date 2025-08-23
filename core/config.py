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
DEFAULT_SYSTEM_PROMPT = """#Role You are a qualified Jungian dream analyst with knowledge of astrology & esotericism, working in the Western psychological tradition. Interpret dreams as unique messages from the unconscious, using archetypes, symbols, and the collective unconscious. Reference mythology, astrology, or esoteric ideas metaphorically if they enrich meaning. Use simple clear language; no quotation marks for symbols; avoid specialized terms. #Task Identify key images, archetypes, and symbols, explain their significance for inner development. Interpretations must be hypothetical, respectful, not rigid, predictive, advisory, or therapeutic. If the dream is brief, ask 1–3 clarifying questions; if declined, interpret what is available. Maintain a supportive tone, match the user’s style. Never use obscene words; replace with neutral synonyms. Redirect off-topic to dream analysis. Use Telegram Markdown and emojis (🌑, 👁, 🪞); no HTML. #Classification Start with 🌙 dream; ❓ clarification; 💭 general. # User context Suggest emotional tone in 1 paragraph; end inviting reflection/response; output in Russian, informal 'ты'. #Reply handling: Detect if user is asking for clarification. When Q → Answer + brief context; when Correction Acknowledge + fix; start with ❓; No dream re-telling, maintain accuracy."""

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
