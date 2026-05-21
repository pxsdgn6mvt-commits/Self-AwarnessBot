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

## DECISION-007 — реальные сигнатуры (2026-05-21)
Источник: Builder адаптации Sprint 003.

_bots dict: ключ — int(tenant_id), НЕ строка bot_token.
  Доступ: _bots[tenant_row['id']]

repo.create_booking(): НЕ принимает pool, client_phone, status как параметры.
  Перед следующим обращением к create_booking() читать реальную сигнатуру в repo.py.

aria_service_items: колонка duration_minutes (не duration_min).

initData parsing: user_id берётся из initData (поле user.id),
  НЕ из тела POST-запроса.

## DECISION-008 — timezone в slot-checking (Sprint 005, 2026-05-21)
scheduled_at хранится в БД как UTC TIMESTAMPTZ.
Для сравнения слотов (HH:MM) конвертировать в tenant.timezone перед сравнением.
Нельзя сравнивать UTC время с локальными HH:MM слотами напрямую.

## DECISION-009 — slot_minutes как fallback для duration (Sprint 006, 2026-05-21)
При overlap-проверке duration конкретной услуги берётся через LEFT JOIN aria_service_items.
Если JOIN не дал результата (услуга не в каталоге) — fallback: tenant.slot_minutes.
Это решение не требует изменения схемы aria_bookings (нет поля service_item_id).
При переходе на service_item_id в будущем — пересмотреть.
