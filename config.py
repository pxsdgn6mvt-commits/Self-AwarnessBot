import os
from dotenv import load_dotenv

load_dotenv()

# Токены и доступ
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Только ты можешь пользоваться ботом

# Мастер-пароль для шифрования (хранится только в .env, никогда в коде)
MASTER_PASSWORD = os.getenv("MASTER_PASSWORD")

# Категории хранилища
CATEGORIES = {
    "passwords": "🔑 Пароли",
    "documents": "📄 Документы",
    "contacts":  "📞 Контакты",
    "notes":     "📝 Заметки",
}

# Сообщения
WELCOME_MESSAGE = (
    "🔐 *Личное хранилище*\n\n"
    "Все данные зашифрованы AES-256.\n"
    "Выбери категорию:"
)
ACCESS_DENIED = "⛔ Доступ запрещён."
