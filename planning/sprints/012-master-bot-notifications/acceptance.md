Sprint 012 — Acceptance Criteria

Must Pass

	•	aria/notifications.py создан, содержит 3 async notify-функции
	•	get_tenant_bot(tenant_id) доступен из aria.main
	•	create_booking() вызывает notify_owner_new_booking через create_task
	•	update_booking_status(..., 'cancelled') вызывает notify_owner_cancelled через create_task
	•	update_booking_time() вызывает notify_owner_rescheduled через create_task
	•	Если get_tenant_bot возвращает None → нет исключения, silent return
	•	TelegramAPIError в send_message → поймана, залогирована, не пробрасывается
	•	5/5 тестов зелёные в tests/test_notifications.py
	•	owner_tg_id берётся из aria_tenants, не из несуществующей aria_masters
	•	server.py не тронут
	•	Нет новых таблиц или ALTER TABLE

Regression

	•	Существующий flow _watch_tenants() работает без изменений
	•	Owner-бот принимает команды как прежде

Notification Text

	•	Новая запись: содержит имя клиента, услугу, дату и время
	•	Отмена: содержит имя клиента, услугу, дату и время
	•	Перенос: содержит старые И новые дату+время
