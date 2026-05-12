import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/vaultbot")

# Таймауты
AUTO_LOCK_SECONDS = 600
SECRET_DELETE_SECONDS = 10
RATE_LIMIT_REQUESTS = 30      # запросов в минуту на пользователя

# Планы
PLAN_FREE = "free"
PLAN_ONETIME = "onetime"
PLAN_PREMIUM = "premium"

FREE_ENTRY_LIMIT = 10
FREE_CATEGORIES = ["passwords", "notes"]

# Стоимость в Stars
PRICE_ONETIME = 1450
PRICE_PREMIUM = 450

# Категории и emoji
CATEGORIES = {
    "passwords":  "🔑",
    "seeds":      "🌱",
    "wallets":    "💼",
    "exchanges":  "📈",
    "twofa":      "🔐",
    "documents":  "📄",
    "contacts":   "👤",
    "notes":      "📝",
}
