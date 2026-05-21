Sprint 011 — Requirements: Master Bot

Business Goal

Мастер получает собственный Telegram-бот с доступом только к своему
расписанию. Владелец салона активирует мастер-бот через owner-бот.

Business Model

Соло-мастер → 1 owner-bot (владелец = мастер)
Салон       → 1 owner-bot + N master-bots (один на мастера)


Users

	•	Владелец — активирует мастер-бот для каждого мастера
	•	Мастер — управляет только своим расписанием через свой бот

Scope

IN

	1.	Схема БД: добавить bot_token TEXT и bot_active BOOLEAN DEFAULT FALSE
в таблицу aria_masters
	2.	_watch_tenants() — подхватывает активные мастер-боты аналогично тенант-ботам
	3.	MasterMiddleware — резолвит master_id из bot.token при каждом апдейте
	4.	master_router — команда /start + все cfg:avail_* хендлеры
	5.	Owner-бот: кнопка "Выдать бот мастеру" → владелец вводит токен мастера

OUT

	•	Доступ мастера к: bookings, clients, income, settings тенанта
	•	Создание токена через BotFather (это делает владелец вручную)
	•	Лимит мастеров (контроль лимитов — отдельный спринт)
	•	Соло-мастер flow (владелец = мастер)

Inputs / Outputs

Input: Владелец вводит bot_token мастера в owner-боте
Output: Мастер-бот запускается, мастер видит /start + availability menu
