Handoff — Sprint 012

You are the Builder Layer. Execute the approved blueprint exactly.

Read First (in this order)

	1.	docs/STATE.md
	2.	planning/sprints/012-master-bot-notifications/requirements.md
	3.	planning/sprints/012-master-bot-notifications/blueprint.md
	4.	aria/main.py — locate _watch_master_bots() and existing Bot management
	5.	aria/db/repo.py — locate create_booking, delete_booking, update_booking

Execute

Step 1 — Expose master bot registry in aria/main.py
Add _master_bots: dict[int, Bot] = {} at module level.
Inside _watch_master_bots(), keep the start/stop logic and also maintain
_master_bots in sync (add on start, remove on stop).
Add: def get_master_bot(master_id: int) -> Bot | None: return _master_bots.get(master_id)

Step 2 — Create aria/notifications.py
Implement 3 async functions as specified in blueprint.md.
Import get_master_bot from aria.main.
All functions: silent return if bot is None, catch TelegramAPIError, log both cases.
Date format: dd.mm.yyyy and HH:MM.

Step 3 — Wire into aria/db/repo.py
After each successful booking write, call the matching notify function via
asyncio.create_task().
If get_booking_details(booking_id) does not exist, create it — minimal SELECT
returning client_name, client_phone, service_name, master_tg_id, dt (and old_dt
for reschedule).
Import notify_* functions lazily inside the function body if needed to avoid
any import-time side effects.

Step 4 — Create tests/test_notifications.py
5 tests as listed in acceptance.md. Use unittest.mock.AsyncMock for bot.
Patch aria.notifications.get_master_bot.

Step 5 — Dry run check
Before writing any file, state which functions in repo.py you found for
create/delete/update booking, and confirm the import chain is acyclic.

Constraints

	•	Do not modify server.py
	•	Do not refactor files outside sprint scope
	•	Do not add new DB tables or columns
	•	If any booking write function is ambiguous (e.g. combined create+update),
stop and describe what you found before proceeding
