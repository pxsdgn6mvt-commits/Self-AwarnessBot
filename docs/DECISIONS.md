# Aria — Architectural Decisions Log

## Key Design Decisions

**Single Dispatcher, multiple bots.** All bots share one `Dispatcher` instance. `dp.feed_update(bot, update)` routes each update with the correct bot object injected. This avoids duplicating router registration.

**TenantMiddleware.** Every update goes through `TenantMiddleware` which looks up the tenant by `bot.token`, caches it 30 seconds, and injects `data["tenant"]` into all handlers. Handlers receive `tenant: TenantConfig` via aiogram's dependency injection.

**Router order is critical.** `setup_router` must be first (handles `/start` when `setup_complete=False`). `chat.router` must be last (catch-all `@router.message()` with no filters).

**PostgresFSMStorage.** FSM states are stored in Postgres so wizard progress survives bot restarts and Railway redeploys. The critical invariant: must store `state.state` (the string `"Group:name"`) NOT `str(state)` (which gives `"<State 'Group:name'>"` with angle brackets that never match `StateFilter`).

**BookingAdapter pattern.** `LocalAdapter` stores everything in Postgres. `GoogleAdapter` stores in both GCal and Postgres. Factory `get_adapter(tenant)` picks the right one based on whether `google_cal_id` and credentials are set. Both adapters have the same interface.

---

## Critical Bugs Found and Fixed

These bugs were ALL caused by the same pattern: **duplicate function/method definitions**. In Python, if a class or module defines the same name twice, the second definition silently overwrites the first.

### Bug 1 — `fsm_storage.py`: `str(state)` stores angle brackets
**File:** `aria/db/fsm_storage.py`, method `set_state`  
**Symptom:** All FSM handlers silently skipped. Log shows: `FSM state active (<State 'OwnerSettings:waiting_cal_id'>) but no handler matched`  
**Root cause:** `str(state)` in aiogram 3 gives `"<State 'Group:name'>"` WITH angle brackets. `StateFilter` compares against `state.state = "Group:name"` WITHOUT brackets. They never match.  
**Fix:**
```python
# BROKEN:
state_str = str(state) if state is not None else None

# CORRECT:
if state is None:
    state_str = None
elif hasattr(state, "state"):
    state_str = state.state   # "Group:name" — no brackets
else:
    state_str = str(state)
```

### Bug 2 — `booking.py`: Duplicate `delete_event` and `get_events`
**File:** `aria/services/booking.py`, class `GoogleAdapter`  
**Symptom:** Schedule always empty even with GCal working. Cancellations crash.  
**Root cause:** Class had two `delete_event` methods and two `get_events` methods. The second definitions (at bottom) used `self._service` and `self._calendar_id` — both undefined attributes (correct attrs are `self._svc` and `self._cal`). The `/test_cal` diagnostic worked because it called `_list_events_sync` directly, bypassing the broken `get_events`.  
**Fix:** Remove the duplicate second definitions entirely.

### Bug 3 — `ai.py`: Duplicate `cancel_booking` block + dead code
**File:** `aria/services/ai.py`, function `_exec_tool`  
**Symptom:** Second `cancel_booking` block unreachable (first block always returns). Dead `cancel_bookings_in_range` code references `date.fromisoformat` but `date` was never imported — would have been a `NameError` if reached.  
**Fix:** Remove the duplicate `cancel_booking` block and the dead `cancel_bookings_in_range` block. Merge the better GCal-string-ID handling into the single remaining block.

### Bug 4 — `repo.py`: Duplicate `get_bookings_in_range`
**File:** `aria/db/repo.py`  
**Symptom:** `TypeError: get_bookings_in_range() takes 2 positional arguments but 3 were given` on every call to `LocalAdapter.get_events()` and `GoogleAdapter.get_events()`.  
**Root cause:** Two definitions. First (correct): `(tenant_id: int, date_from: datetime, date_to: datetime)`. Second (broken override): `(date_from: "date", date_to: "date")` — no `tenant_id`, wrong types.  
**Fix:** Remove the second definition. Also remove the orphaned `get_bookings_by_gcal_ids` function that was only referenced by the now-removed duplicate `get_events`.

### Summary
All four bug groups were introduced during a code merge/refactor where old code wasn't deleted when new versions were written. **Whenever refactoring, always delete the old definition before writing the new one, or search the file for duplicate names.**

---

## S1 Voice Feature Bugs (2026-05-19)

### Bug 5 — `~F.text.in_(set)` matches voice messages (text=None)
**Files:** `aria/handlers/quick.py`, `start.py`, `email_setup.py`, `menu.py`  
**Symptom:** Voice messages silently consumed by FSM step handlers. No response from bot.  
**Root cause:** Magic filter `~F.text.in_(frozenset(...))` evaluates `False` when `msg.text is None`, then `~False = True` — so FSM handlers matched voice and crashed on `message.text.strip()`.  
**Fix:** Add explicit `F.text` as an additional filter on all FSM step handlers:
```python
# BROKEN — matches voice (text=None):
@router.message(QuickBook.date, ~F.text.in_(MAIN_KB_TEXTS))

# CORRECT — requires text to be non-None first:
@router.message(QuickBook.date, F.text, ~F.text.in_(MAIN_KB_TEXTS))
```

### Bug 6 — Russian morphology: "запиши" not matched by "запис"
**File:** `aria/handlers/chat.py`, `_BOOKING_VERBS` list  
**Symptom:** "Запиши Вику на завтра" → shows tomorrow's schedule instead of starting a booking.  
**Root cause:** Russian morphology — "запиши" (imperative) is зап+**ИШ**+и, while "запись"/"записать" is зап+**ИС**+ь/ать. The substring `"запис"` is NOT in `"запиши"`.  
**Fix:** Add `"запиш"` to booking verbs:
```python
_BOOKING_VERBS = [
    "запис", "запиш",  # запись/записать + запиши/запишешь (разные морфемы)
    ...
]
```

### Bug 7 — TenantMiddleware returns `tenant=None` on DB cache miss
**File:** `aria/middleware.py`  
**Symptom:** After DB connection blip, all messages silently dropped for up to 30 seconds.  
**Root cause:** When cache TTL expired AND DB query failed, code fell through to `tenant = None`.  
**Fix:** Added `_last_good: dict[str, TenantConfig]` permanent dict. On successful DB fetch, stores config there. On DB error with empty cache, promotes last good config back:
```python
_last_good: dict[str, TenantConfig] = {}

# On error:
if cached is None and bot.token in TenantMiddleware._last_good:
    fallback = TenantMiddleware._last_good[bot.token]
    TenantMiddleware._cache[bot.token] = (fallback, now)
    cached = TenantMiddleware._cache[bot.token]
```

---

## Lessons Learned

- **Duplicate definitions in Python are silent killers.** No warning, no error — the second definition overwrites the first. Always grep for duplicate function names before merging.
- **aiogram 3 `str(state)` is a trap.** Use `state.state` to get the bare string without angle brackets.
- **aiogram 3 magic filters with `~` and `None`.** `~F.text.in_(set)` is `True` when `text=None` — always guard with explicit `F.text` first on handlers where voice/photo messages could arrive.
- **Russian morphology matters.** Imperative verb roots differ from noun/infinitive roots. Test bypass logic with all imperative forms.
- **TenantMiddleware must never return `None` for an active bot.** The fallback dict pattern protects against transient DB errors without user impact.
