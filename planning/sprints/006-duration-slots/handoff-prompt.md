You are the Builder Layer. Execute the approved blueprint exactly.
Source of truth: the project folder, not this chat.

## Step 1 — Read first

1. docs/STATE.md
2. planning/sprints/006-duration-slots/requirements.md
3. aria/db/repo.py — find get_slots_on_date (current signature and SQL)
4. aria/handlers/quick.py — find _time_kb (how slots are filtered)
5. aria/main.py — find _handle_slots (current inline filtering)

## Step 2 — Dry run

Output:
- Current return type of get_slots_on_date
- Proposed new return type and SQL (with JOIN + COALESCE fallback)
- Overlap formula: booked_start < slot_end AND booked_end > slot_start
- Where slots_overlap util will live

Stop if anything is ambiguous.

## Step 3 — Execute

1. aria/db/repo.py
  - Modify get_slots_on_date: LEFT JOIN + COALESCE, return list[tuple[datetime, int]]
  - Add slots_overlap(slot_start_min, slot_min, bookings) -> bool

2. aria/handlers/quick.py _time_kb
  - Replace: booked = {HH:MM set}; if label not in booked
  - With: booked_intervals = [(start_min, dur)...]; if not repo.slots_overlap(...)

3. aria/main.py _handle_slots
  - Replace inline booked set + string filter
  - With: repo.get_slots_on_date + repo.slots_overlap

## Step 4 — Summary

Plain text only, no markdown tables.

FILES MODIFIED: list
ASSUMPTIONS: list
AC STATUS:
  AC-1 repo returns (start, duration): OK/WARN
  AC-2 overlap check quick.py: OK/WARN
  AC-3 overlap check handle_slots: OK/WARN
  AC-4 shared util no duplication: OK/WARN
OPEN QUESTIONS: list or none
