Handoff — Sprint 012 (revised after dry-run blockers)

You are the Builder Layer. Execute the approved blueprint exactly.

Critical context (read before anything else)

The previous sprint 012 dry-run revealed that aria_masters table does NOT exist
and _watch_master_bots() does NOT exist. This revised sprint works with the
ACTUAL codebase. "Owner" = salon owner = tg_id in aria_tenants.

Read First (in this order)

	1.	docs/STATE.md
	2.	planning/sprints/012-master-bot-notifications/requirements.md
	3.	planning/sprints/012-master-bot-notifications/blueprint.md
	4.	aria/main.py — locate _watch_tenants() and the tenant Bot dict
	5.	aria/db/repo.py — locate create_booking, update_booking_status,
update_booking_time; check for existing tg_id and booking-detail helpers

Dry-run first (mandatory)

Before writing any file, report:

	•	Exact name and line number of the tenant Bot dict in main.py
	•	Whether get_tenant_owner_tg_id or equivalent already exists in repo.py
	•	Whether get_booking_details or equivalent already exists in repo.py
	•	Confirm import chain is acyclic

If anything is ambiguous or missing from the above — stop and report, do not invent.

Execute (after dry-run confirmed)

Step 1 — aria/main.py
Add def get_tenant_bot(tenant_id: int) -> Bot | None using the existing
tenant Bot dict. Do not change _watch_tenants() logic.

Step 2 — aria/notifications.py (new file)
Three async functions: notify_owner_new_booking, notify_owner_cancelled,
notify_owner_rescheduled. Silent return if bot is None. Catch TelegramAPIError.
Date format: dd.mm.yyyy, time: HH:MM.

Step 3 — aria/db/repo.py
Add get_tenant_owner_tg_id(tenant_id) if not present.
Add get_booking_details(booking_id) if not present.
Wire asyncio.create_task(notify_owner_*(...)) into the three booking mutation
functions. Import notify functions inside the function body to avoid circular
import issues at module load time.

Step 4 — tests/test_notifications.py (new file)
5 tests. Patch aria.notifications.get_tenant_bot with AsyncMock.
Cover: new booking, cancelled, rescheduled, no-bot silent return, TelegramAPIError swallowed.

Constraints

	•	No new DB tables or ALTER TABLE
	•	Do not modify server.py
	•	Do not refactor files outside sprint scope
	•	tg_id comes from aria_tenants, never from aria_masters
