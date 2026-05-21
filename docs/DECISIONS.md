# DECISIONS.md — Architecture Decisions

## DECISION-001 — Multi-tenant polling (2026-05-21)
Контекст: каждый тенант имеет отдельный bot_token.
Решение: один процесс, N polling-задач (asyncio tasks), один shared Dispatcher.

## DECISION-002 — PostgresFSMStorage (2026-05-21)
Контекст: бот на Railway перезапускается, MemoryStorage теряет состояние.
Решение: FSM state в PostgreSQL (aria_fsm_states), переживает рестарты.

## DECISION-003 — callback_data паттерн (2026-05-21)
Контекст: Telegram ограничивает callback_data до 64 байт.
Решение: в callback_data передаём только числовой ID сущности.
Имена, цены, длительности — в FSM state через dict (items_info).
Применять этот паттерн во всех будущих inline-хендлерах.

## DECISION-004 — client_phone nullable (2026-05-21)
Контекст: клиент может не иметь возможности поделиться номером.
Решение: client_phone TEXT (nullable). Уведомление владельцу показывает
"не указан" если NULL. Бронь сохраняется в любом случае.

## DECISION-005 — клиентский routing (2026-05-21)
Контекст: один бот обслуживает и владельца и клиентов одного тенанта.
Решение: tenant.is_owner(user_id) — единственный признак ветвления.
client_booking.router регистрируется ДО owner-роутеров в main.py.
owner_tg_id IS NULL → пользователь становится владельцем (setup flow).
