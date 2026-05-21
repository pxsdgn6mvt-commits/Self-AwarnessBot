Sprint 011 — Blueprint

Files to Modify

	•	aria/db/repo.py — 3 новые функции
	•	aria/db/models.py — миграция aria_masters
	•	aria/main.py — регистрация master polling + _watch_master_bots()
	•	aria/handlers/masters.py — кнопка выдачи токена владельцем

Files to Create

	•	aria/middlewares/master.py — MasterMiddleware
	•	aria/handlers/master_bot.py — master_router

Files to Read

	•	aria/main.py — текущий _watch_tenants() паттерн
	•	aria/middlewares/ — существующий TenantMiddleware для образца
	•	aria/handlers/availability.py — cfg:avail_* хендлеры (реиспользуем)
	•	docs/DOMAIN.md — схема aria_masters

Technical Approach

Шаг 1 — Миграция БД

ALTER TABLE aria_masters
  ADD COLUMN bot_token TEXT,
  ADD COLUMN bot_active BOOLEAN DEFAULT FALSE;


Шаг 2 — repo.py

async def get_active_master_bots(conn) -> list[dict]:
    # SELECT id, tenant_id, bot_token FROM aria_masters
    # WHERE bot_active = TRUE AND bot_token IS NOT NULL

async def set_master_bot_token(conn, master_id, token) -> None:
    # UPDATE aria_masters SET bot_token=$1, bot_active=TRUE
    # WHERE id=$2

async def get_master_by_token(conn, token) -> dict | None:
    # SELECT id, tenant_id FROM aria_masters
    # WHERE bot_token=$1 AND bot_active=TRUE


Шаг 3 — MasterMiddleware

# aria/middlewares/master.py
class MasterMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        bot_token = data['bot'].token
        master = await repo.get_master_by_token(conn, bot_token)
        if not master:
            return  # игнорировать апдейт
        data['master_id'] = master['id']
        data['tenant_id'] = master['tenant_id']
        return await handler(event, data)


Шаг 4 — master_router

# aria/handlers/master_bot.py
master_router = Router()

@master_router.message(Command('start'))
async def master_start(message, master_id, tenant_id):
    # Приветствие + кнопка "Моё расписание"
    # → открывает cfg:avail:{master_id}

# Все cfg:avail_* хендлеры уже есть в availability.py
# master_router включает availability_router как вложенный


Шаг 5 — _watch_master_bots() расширение

# В main.py рядом с существующим _watch_tenants()
async def _watch_master_bots():
    # Аналогичный polling loop для мастер-ботов
    # Читает get_active_master_bots()
    # Запускает/останавливает Dispatcher per master bot
    # Регистрирует MasterMiddleware + master_router


Шаг 6 — Owner-бот UI

В aria/handlers/masters.py — в карточке мастера добавить кнопку:
[🤖 Выдать бот] → cfg:master_token:{master_id}

FSM: владелец вводит токен → валидация (проверить что токен рабочий
через bot.get_me()) → set_master_bot_token() → подтверждение


No Changes

	•	aria/handlers/availability.py — не трогать, переиспользуется
	•	server.py — не трогать
	•	Схема aria_availability — не трогать
