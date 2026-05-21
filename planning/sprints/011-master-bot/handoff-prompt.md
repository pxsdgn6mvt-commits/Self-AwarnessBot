Sprint 011 — Handoff Prompt for Builder

Read these files before starting:

	•	docs/STATE.md
	•	docs/DOMAIN.md
	•	aria/main.py — текущий _watch_tenants() паттерн
	•	aria/middlewares/ — существующий middleware для образца
	•	aria/handlers/availability.py — cfg:avail_* хендлеры
	•	planning/sprints/011-master-bot/requirements.md
	•	planning/sprints/011-master-bot/blueprint.md
	•	planning/sprints/011-master-bot/acceptance.md

Task

1. Database Migration

ALTER TABLE aria_masters
  ADD COLUMN bot_token TEXT,
  ADD COLUMN bot_active BOOLEAN DEFAULT FALSE;


2. repo.py — добавить 3 функции

	•	get_active_master_bots(conn)
	•	set_master_bot_token(conn, master_id, token)
	•	get_master_by_token(conn, token)

3. Создать aria/middlewares/master.py

MasterMiddleware резолвит master_id + tenant_id из bot.token.
Образец: смотри существующий TenantMiddleware.

4. Создать aria/handlers/master_bot.py

	•	master_router с /start хендлером
	•	Включить availability_router как вложенный (include_router)
	•	Не дублировать cfg:avail_* логику

5. Расширить aria/main.py

	•	Добавить _watch_master_bots() рядом с _watch_tenants()
	•	Регистрировать MasterMiddleware + master_router для каждого мастер-бота

6. aria/handlers/masters.py

	•	Добавить кнопку "🤖 Выдать бот" в карточку мастера
	•	FSM: ввод токена → bot.get_me() валидация → set_master_bot_token()

Dry Run First

Перед написанием кода выведи:

	•	Список всех файлов которые будут изменены/созданы
	•	Сигнатуры 3 новых repo функций
	•	Как master_router включает availability_router

Если что-то в blueprint неоднозначно — остановись и спроси.
Не трогай: server.py, aria/handlers/availability.py, aria_availability схему.
