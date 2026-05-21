Sprint 012 — Booking Push Notifications to Salon Owner

Business Goal

Когда запись создаётся, отменяется или переносится — владелец салона получает
мгновенный push в свой бот. Сейчас владелец узнаёт о записях только заглядывая
в расписание вручную.

Users

	•	Owner (владелец салона) — получает push через существующий tenant-бот
	•	Клиент — (будущее) источник записи через Mini App, вне scope

Terminology (исправлено)

	•	"Мастер" = владелец салона = tg_id в таблице aria_tenants
	•	"Master bot" = бот тенанта, уже запущенный через _watch_tenants()
	•	Никакой таблицы aria_masters нет и не создаётся

Scope

Уведомить владельца салона когда:

	1.	Создана новая запись к нему (create_booking)
	2.	Запись отменена (update_booking_status(id, 'cancelled'))
	3.	Запись перенесена (update_booking_time(id, new_time))

Out of scope

	•	Новые таблицы или колонки в БД
	•	Mini App → notification
	•	Отдельные боты на мастеров
	•	Подтверждение доставки

Message Format (Russian)

📅 Новая запись!
Клиент: {client_name} ({client_phone})
Услуга: {service_name}
Дата: {date} в {time}


❌ Запись отменена
Клиент: {client_name}
Услуга: {service_name}
Дата: {date} в {time}


🔄 Запись перенесена
Клиент: {client_name}
Услуга: {service_name}
Было: {old_date} в {old_time}
Стало: {new_date} в {new_time}
