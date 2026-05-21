Sprint 012 — Blueprint

Architecture Decision

Notifications must be sent from inside the booking write path, not via a
separate polling loop. The _watch_master_bots() coroutine in main.py already
maintains a live dict of master_id → Bot instances. We expose that dict via a
module-level accessor so repo/handler code can call it without circular imports.

Files to Modify

1. aria/main.py

	•	Add module-level dict: _master_bots: dict[int, Bot] = {}
	•	Populate it inside _watch_master_bots() (already does start/stop — also
update this dict in sync)
	•	Add public accessor: def get_master_bot(master_id: int) -> Bot | None

2. aria/notifications.py ← NEW FILE

	•	async def notify_master_new_booking(master_id, tg_id, client_name, client_phone, service_name, dt: datetime) -> None
	•	async def notify_master_cancelled(master_id, tg_id, client_name, service_name, dt: datetime) -> None
	•	async def notify_master_rescheduled(master_id, tg_id, client_name, service_name, old_dt: datetime, new_dt: datetime) -> None
	•	Each function: calls get_master_bot(master_id), returns silently if None
(master has no bot yet — not an error)
	•	Uses bot.send_message(tg_id, text) wrapped in try/except TelegramAPIError
	•	Logs success and failure via standard logging

3. aria/db/repo.py

	•	Identify the 3 booking write functions:
create_booking(), delete_booking(), update_booking()
	•	After successful DB write in each, fetch enriched data needed for notification
(client name/phone, service name, master tg_id) — use existing repo helpers or
add minimal get_booking_details(booking_id) if not present
	•	Call corresponding notify_master_*() — use asyncio.create_task() so DB
path never blocks on Telegram delivery

4. aria/db/models.py

	•	No schema changes required

5. tests/test_notifications.py ← NEW FILE

	•	Mock get_master_bot() to return a mock Bot
	•	Test: new booking → bot.send_message called with correct text
	•	Test: no master bot → function returns without error
	•	Test: TelegramAPIError → swallowed, no exception propagates
	•	Test: cancelled booking → correct cancel text
	•	Test: rescheduled → both old and new datetime in message

Implementation Order

	1.	main.py — expose get_master_bot()
	2.	aria/notifications.py — pure async functions, no side effects at import
	3.	aria/db/repo.py — wire asyncio.create_task(notify_*(...)) at write points
	4.	tests/test_notifications.py — 5 tests

Risk: circular import

notifications.py imports from main.py (get_master_bot).
main.py imports nothing from notifications.py.
repo.py imports from notifications.py.
main.py imports from repo.py.
→ Chain is acyclic. Safe.
