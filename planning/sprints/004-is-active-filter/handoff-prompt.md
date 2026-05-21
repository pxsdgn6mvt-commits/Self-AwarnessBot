You are the Builder Layer. Execute the approved blueprint exactly.
Source of truth: the project folder, not this chat.

## Step 1 — Read first

1. docs/STATE.md
2. docs/DECISIONS.md
3. planning/sprints/004-is-active-filter/requirements.md
4. aria/db/models.py — find ALTER TABLE block, understand migration pattern
5. aria/main.py — find _handle_categories and _handle_services SQL queries
6. aria/handlers/client_booking.py — find choosing_category and choosing_service queries
7. aria/handlers/setup.py — understand existing owner UI for services

## Step 2 — Dry run

Output:
- Exact SQL for both ALTER TABLE migrations
- Exact lines in main.py and client_booking.py to update (show before/after)
- What exists in setup.py for service management (describe, do not assume)
- Proposed owner toggle mechanism based on what setup.py actually contains

## Step 3 — Execute

1. aria/db/models.py — add both ALTER TABLE migrations
2. aria/main.py — add WHERE is_active = true to _handle_categories, _handle_services
3. aria/handlers/client_booking.py — add WHERE is_active = true to both queries
4. aria/handlers/setup.py — add toggle mechanism (based on dry run finding)

## Step 4 — Summary

Plain text only, no markdown tables. One section per line.

FILES MODIFIED: list
ASSUMPTIONS: list
AC STATUS:
  AC-1 migration: OK/WARN
  AC-2 API filter: OK/WARN
  AC-3 FSM filter: OK/WARN
  AC-4 owner toggle: OK/WARN
OPEN QUESTIONS: list or none
