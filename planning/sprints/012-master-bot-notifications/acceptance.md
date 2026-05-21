Sprint 012 — Acceptance Criteria

Must Pass

	•	aria/notifications.py exists with 3 async notify functions
	•	get_master_bot(master_id) accessible from aria.main
	•	_master_bots dict updated by _watch_master_bots() on every poll cycle
	•	create_booking() triggers notify_master_new_booking via create_task
	•	delete_booking() triggers notify_master_cancelled via create_task
	•	update_booking() triggers notify_master_rescheduled via create_task
(only when date/time fields actually change)
	•	If master has no bot (get_master_bot returns None) → no exception, silent return
	•	TelegramAPIError in send_message → caught, logged, not re-raised
	•	5/5 tests green in tests/test_notifications.py
	•	Owner-bot booking flow unchanged (no regression)
	•	server.py untouched

Notification Text Checks

	•	New booking message contains: клиент name, phone, service, date+time
	•	Cancelled message contains: клиент name, service, date+time
	•	Rescheduled message contains: old date+time AND new date+time

Not Required This Sprint

	•	Delivery confirmation
	•	Mini App booking → notification
	•	Client-triggered notifications
