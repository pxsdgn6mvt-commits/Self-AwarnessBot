import os
from dotenv import load_dotenv

load_dotenv()

# Токены и доступ
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip())

# Мастер-пароль для шифрования (хранится только в .env)
MASTER_PASSWORD = os.getenv("MASTER_PASSWORD")

# Категории хранилища
CATEGORIES = {
    "passwords":  "🔑 Пароли",
    "documents":  "📄 Документы",
    "contacts":   "📞 Контакты",
    "notes":      "📝 Заметки",
}

# Сообщения
WELCOME_MESSAGE = (
    "🔐 *Личное хранилище*\n\n"
    "Все данные зашифрованы AES-256.\n"
    "Выбери категорию:"
)
ACCESS_DENIED = "🚫 Доступ запрещён."

# Время автоблокировки (секунды)
AUTO_LOCK_SECONDS = 600  # 10 минут

# Время автоудаления сообщений с секретами (секунды)
SECRET_DELETE_SECONDS = 10
