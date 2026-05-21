Sprint 011 — Acceptance Criteria

Database

	•	aria_masters.bot_token TEXT существует
	•	aria_masters.bot_active BOOLEAN DEFAULT FALSE существует

repo.py

	•	get_active_master_bots() возвращает только active=TRUE + token NOT NULL
	•	set_master_bot_token() обновляет token + active=TRUE
	•	get_master_by_token() резолвит master_id + tenant_id по токену

MasterMiddleware

	•	Резолвит master_id и tenant_id из bot.token
	•	Апдейты без валидного токена игнорируются

master_router

	•	/start возвращает приветствие с именем мастера
	•	/start показывает кнопку "Моё расписание"
	•	Кнопка открывает cfg:avail:{master_id} (из availability.py)
	•	cfg:avail_* хендлеры работают в контексте мастера
	•	Нет доступа к bookings / clients / income / settings

Owner-бот

	•	Кнопка "🤖 Выдать бот" в карточке мастера
	•	FSM принимает токен, валидирует через bot.get_me()
	•	После сохранения — мастер-бот подхватывается polling-ом

Integration

	•	Два мастера с разными токенами работают одновременно
	•	Owner-бот продолжает работать без деградации
