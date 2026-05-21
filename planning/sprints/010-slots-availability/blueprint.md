# Sprint 010 — Blueprint

## Files to Modify
- server.py — единственный файл изменяется

## Files NOT to Touch
- repo.py, main.py, handlers/, miniapp/

## Technical Approach

### Step 1 — Accept master param
```python
master_id = request.args.get("master", type=int)  # None если не передан
```

### Step 2 — Load availability records
Inside existing `_fetch()` coroutine via same `conn`:
```sql
SELECT is_open, time_from, time_to
FROM aria_availability
WHERE tenant_id = $1
  AND master_id = $2
  AND date = $3
```
Only executed if master_id is not None.

### Step 3 — Apply priority rules
```python
def _apply_availability(slots, avail_rows, slot_minutes):
    # Rule 2: closed day
    if any(not r["is_open"] and r["time_from"] is None for r in avail_rows):
        return []

    # Rule 3: custom hours — rebuild slots
    custom = [r for r in avail_rows if r["is_open"] and r["time_from"]]
    if custom:
        slots = _generate_slots(custom[0]["time_from"],
                                custom[0]["time_to"],
                                slot_minutes)

    # Rule 1: blocked slots
    blocked = {r["time_from"].strftime("%H:%M")
               for r in avail_rows
               if not r["is_open"] and r["time_from"]}
    return [s for s in slots if s not in blocked]
```

### Step 4 — Wire into existing flow
Call `_apply_availability()` after booked-slots exclusion, before `return jsonify(slots)`.

## Sync Context Note
`/api/slots` runs in Flask sync context via `asyncio.run()`.
Use inline SQL via same `conn` — do NOT import repo.py (event loop conflict).

## No Schema Changes
