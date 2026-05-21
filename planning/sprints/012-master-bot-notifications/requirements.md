Sprint 012 — Master Bot Push Notifications

Business Goal

When a booking is created, modified, or cancelled — the affected master receives an
instant push notification in their personal bot. Masters currently learn about
bookings only by manually checking their schedule. This sprint closes that gap.

Users

	•	Master — receives push in their bot (via master_bot dispatcher)
	•	Owner — triggers notifications indirectly by managing bookings in owner-bot
	•	Client — (future) triggers notifications via Mini App booking (out of scope)

Scope

Notify master bot when:

	1.	New booking created for this master (any source: owner-bot FSM)
	2.	Booking cancelled / deleted
	3.	Booking rescheduled (date or time changed)

Out of scope:

	•	Client-side booking flow (Sprint future)
	•	Mini App webhook → notification (Sprint future, blocked on Mini App auth)
	•	Bulk/broadcast notifications
	•	Read receipts or delivery confirmation

Inputs

	•	Existing booking write functions in aria/db/repo.py
	•	get_active_master_bots() → maps master_id → bot instance (already in _watch_master_bots)
	•	Master's telegram tg_id from aria_masters table

Outputs

	•	Push message sent to master's tg_id via their bot instance
	•	No new DB tables required
	•	Notification text in Russian, consistent with existing bot tone

Notification Message Format

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
