# Sprint 010 — Handoff Prompt for Builder

## Read First
1. docs/STATE.md
2. docs/DOMAIN.md (aria_availability schema)
3. planning/sprints/010-slots-availability/requirements.md
4. planning/sprints/010-slots-availability/blueprint.md
5. planning/sprints/010-slots-availability/acceptance.md

## Then Read
- server.py lines 221–279 (the /api/slots endpoint)

## Task
Modify **only server.py**. Do not touch any other file.

1. Add optional `?master=X` (int) parameter to /api/slots
2. If master is provided: query aria_availability inline using the
   same `conn` pattern already used in the function. Do NOT import
   or call repo.py — avoid asyncio event loop conflicts.
3. Implement `_apply_availability(slots, avail_rows, slot_minutes)`
   as a pure helper function (no DB calls inside).
4. Apply priority rules exactly as specified in requirements.md.
5. If master is not provided: skip availability logic entirely
   (backward compatibility).

## Priority Rules (repeat for clarity)
```
Rule 2 first:  is_open=FALSE + time_from IS NULL  → return []
Rule 3 second: is_open=TRUE  + time_from NOT NULL → rebuild slots
Rule 1 last:   is_open=FALSE + time_from NOT NULL → remove slot
```

## Dry Run (output before writing code)
- Which lines in server.py will change
- Signature of `_apply_availability()`
- The SQL query for aria_availability

## Constraints
- Only server.py changes
- No repo.py imports inside server.py
- No schema changes
- No format change in API response

## Completion Summary Format
### Lines Changed in server.py
### _apply_availability() Signature
### SQL Query Used
### Acceptance Criteria Status [✅/❌]
### Ready for Sprint 011: YES/NO
