# Architecture Decisions

## DECISION-001 — Multi-tenant polling architecture
Один asyncio process (`aria/main.py`) держит по одному aiogram Bot + polling loop на каждого тенанта.
Watcher каждые 10 с проверяет новых/удалённых тенантов и запускает/останавливает задачи.

## DECISION-002 — Flask для маркетингового сайта
`server.py` (gunicorn) — отдельный процесс для landing page и /api/chat.
Не имеет доступа к aria/ asyncio runtime, pool или _bots.

## DECISION-003 — asyncpg pool как единственный DB-клиент
Нет ORM. Все запросы — raw SQL через asyncpg. Pool инициализируется один раз в `init_db()`,
доступен через `repo._p()` или `await repo.get_pool(dsn)`.

## DECISION-004 — PostgresFSMStorage для aiogram FSM
FSM state хранится в `aria_fsm_states` (postgres), переживает рестарты.

## DECISION-005 — APScheduler для cron-задач
Ежедневные reminder'ы и reactivation запускаются через APScheduler внутри того же процесса.

## DECISION-006 — API layer: aiohttp внутри aria/main.py (2026-05-21)
Контекст: server.py оказался Flask (gunicorn, изолирован от aria/).
Blueprint предполагал aiohttp в server.py — неверное допущение.

Реальная архитектура процессов (Procfile):
  web:    gunicorn server:app   ← Flask, маркетинг, нет доступа к pool/_bots
  worker: python -m aria.main  ← asyncio, pool, _bots dict

Решение: aiohttp.web сервер запускается как asyncio task внутри aria/main.py
рядом с polling loop. Порт: env PORT_API (default 8081).
Преимущества: прямой доступ к db pool и _bots dict, нулевые накладные расходы,
не нужен третий Railway process.

Следствие: Mini App делает запросы НЕ на server.py, а на отдельный порт/путь.
В Railway добавить переменную PORT_API и настроить routing если нужно.
