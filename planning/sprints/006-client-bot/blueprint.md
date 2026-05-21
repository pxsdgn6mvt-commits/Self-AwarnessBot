# Sprint 006 — Blueprint

## Reading Order for Builder
1. docs/STATE.md
2. docs/DOMAIN.md — структура aria_bookings, поле client_tg_id
3. docs/DECISIONS.md
4. planning/sprints/006-client-bot/requirements.md
5. development.md — секции про multi-tenant polling, main.py, _tg_notify
6. aria/main.py — понять как регистрируется owner-бот, найти точку для второго бота
7. aria/handlers/start.py — паттерн хендлера /start для референса
8. server.py — найти POST /api/bookings и _tg_notify()
9. aria/config.py — найти MINIAPP_URL и паттерн чтения env vars
10. .env.example — найти где добавить CLIENT_BOT_TOKEN

## Change 1 — aria/handlers/client_bot.py (новый файл)

```python
import os
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

client_router = Router()

@client_router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    tenant_id = None
    if len(args) > 1 and args[1].startswith("tenant_"):
        tenant_id = args[1].replace("tenant_", "")

    if not tenant_id:
        await message.answer("Используйте ссылку от вашего мастера для записи.")
        return

    miniapp_url = os.getenv("MINIAPP_URL", "")
    webapp_url = f"{miniapp_url}?tenant_id={tenant_id}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться", web_app=WebAppInfo(url=webapp_url))
    ]])

    await message.answer("Добро пожаловать! Нажмите кнопку чтобы выбрать время:",
                         reply_markup=keyboard)
```

Прочитать паттерн из aria/handlers/start.py перед написанием.

## Change 2 — aria/main.py

Найти где инициализируется owner-бот, добавить рядом:

```python
CLIENT_BOT_TOKEN = os.getenv("CLIENT_BOT_TOKEN", "")

if CLIENT_BOT_TOKEN:
    client_bot = Bot(token=CLIENT_BOT_TOKEN)
    # добавить polling рядом с owner-bot polling
else:
    log.warning("CLIENT_BOT_TOKEN not set — client bot disabled")
```

Если CLIENT_BOT_TOKEN не задан — graceful degradation, owner-боты работают.

## Change 3 — server.py: client_tg_id + уведомление мастера

### 3a. client_tg_id
- Принять из request body как опциональное поле
- Если колонка есть в aria_bookings — сохранить
- Если нет — написать ALTER TABLE в summary, не выполнять

### 3b. Уведомление мастеру
После успешного INSERT вызвать _tg_notify() с текстом:
- Имя клиента, услуга, дата, время, пометка "через Mini App"
- Найти реальную сигнатуру _tg_notify() перед написанием

## Change 4 — .env.example

```
CLIENT_BOT_TOKEN=         # Токен клиентского бота (BotFather), опционально
```

## Files to Create
| Файл | Описание |
|---|---|
| aria/handlers/client_bot.py | Хендлеры клиентского бота |

## Files to Modify
| Файл | Изменение |
|---|---|
| aria/main.py | Регистрация второго бота и polling |
| server.py | client_tg_id + уведомление мастера |
| .env.example | CLIENT_BOT_TOKEN |

## Files NOT to Touch
- miniapp/ — любые файлы
- aria/handlers/start.py — owner-бот хендлеры не трогать
- APScheduler, notify_admin, тесты
