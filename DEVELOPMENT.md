# Aria — Developer Build Guide

Everything learned the hard way. Read this before writing a single line of code.

---

## Stack

| Layer | Library | Version |
|---|---|---|
| Telegram | aiogram | 3.13.x |
| AI | anthropic (Claude Haiku) | ≥ 0.49 |
| Database | asyncpg (PostgreSQL) | 0.30.x |
| Scheduler | APScheduler | 3.10.x |
| Google Calendar | google-api-python-client + google-auth | 2.x |
| Config | python-dotenv | 1.x |
| Deployment | Railway | — |

---

## Critical aiogram 3 Rules

### 1. Multi-bot polling — NEVER use `dp.start_polling()`

`dp.start_polling()` has an internal lock. If you call it from multiple asyncio tasks (one per bot), the first task acquires the lock forever and all others block silently.

**Wrong:**
```python
async def run_bot(bot):
    await dp.start_polling(bot)  # blocks all other bots
```

**Correct — one shared dispatcher, custom polling loop per bot:**
```python
async def _poll_bot(bot: Bot, dp: Dispatcher, tenant_id: int) -> None:
    allowed = dp.resolve_used_update_types()
    offset = 0
    me = await bot.get_me()
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30, allowed_updates=allowed)
            for update in updates:
                await dp.feed_update(bot, update)
                offset = update.update_id + 1
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("get_updates error, retry in 5s")
            await asyncio.sleep(5)
```

One `Dispatcher` created once. All bots feed into it. Router included once.

### 2. BaseFilter — NEVER use typed parameter DI

In aiogram 3, `BaseFilter.__call__` does NOT support named-parameter dependency injection the way handlers do. Typed params are always `None`.

**Wrong:**
```python
class SetupDone(BaseFilter):
    async def __call__(self, message: Message, tenant: TenantConfig = None) -> bool:
        return tenant is not None  # tenant is ALWAYS None here
```

**Correct — use `**kwargs`:**
```python
class SetupDone(BaseFilter):
    async def __call__(self, message: Message, **kwargs) -> bool:
        tenant = kwargs.get("tenant")
        return tenant is not None and tenant.setup_complete
```

### 3. Routers included ONCE on the shared Dispatcher

Including a router more than once (e.g. once per tenant) causes `RuntimeError: Router already attached`.

```python
def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(TenantMiddleware())
    dp.include_router(setup_router)   # once
    dp.include_router(admin.router)   # once
    dp.include_router(start.router)   # once
    dp.include_router(chat.router)    # once
    return dp
```

### 4. Router order matters

aiogram processes routers in the order they are included. The catch-all chat handler must be **last**.

```python
dp.include_router(setup_router)  # FSM wizard — first
dp.include_router(admin.router)  # /add_bot etc
dp.include_router(start.router)  # /start, /help, owner commands
dp.include_router(chat.router)   # catch-all — LAST
```

### 5. Gate handlers with filters, not early returns

Wrong pattern — silently swallows the update, blocks other routers:
```python
@router.message(CommandStart())
async def cmd_start(message, tenant):
    if tenant.setup_complete:
        return  # wrong — update is consumed, nothing else runs
```

Correct — use filters as decorators:
```python
@router.message(CommandStart(), SetupRequired())
async def setup_start(...): ...

@router.message(CommandStart(), SetupDone())
async def cmd_start(...): ...
```

---

## Middleware Pattern

The middleware resolves `TenantConfig` from `bot.token` on every update and injects it into `data["tenant"]`. Use a short TTL cache (30s) to avoid DB hammering.

```python
class TenantMiddleware(BaseMiddleware):
    _cache: dict[str, tuple[TenantConfig, float]] = {}

    async def __call__(self, handler, event, data):
        bot = data.get("bot")
        now = time.monotonic()
        cached = self._cache.get(bot.token)
        if cached is None or (now - cached[1]) > 30:
            row = await repo.get_tenant_by_token(bot.token)
            if row:
                self._cache[bot.token] = (TenantConfig.from_record(dict(row)), now)
        if bot.token in self._cache:
            data["tenant"] = self._cache[bot.token][0]
        return await handler(event, data)

    @classmethod
    def invalidate(cls, bot_token: str) -> None:
        cls._cache.pop(bot_token, None)
```

Call `TenantMiddleware.invalidate(token)` any time you update the tenant record in the DB.

---

## Timezone Handling

All datetimes are stored in PostgreSQL as `TIMESTAMPTZ` (UTC). Conversion to/from tenant local time happens at the edges.

### Parsing user input (local → UTC)
```python
def parse_datetime(date_str: str, time_str: str, tz_str: str = "UTC") -> datetime | None:
    from zoneinfo import ZoneInfo
    d = date.fromisoformat(date_str)
    h, m = map(int, time_str.split(":"))
    local_dt = datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(tz_str))
    return local_dt.astimezone(timezone.utc)
```

### Displaying schedule (UTC → local)
```python
local_dt = row["scheduled_at"].astimezone(ZoneInfo(tenant.timezone or "UTC"))
time_str = local_dt.strftime("%H:%M")
```

### Day boundaries for queries (local midnight → UTC)
```python
tz = ZoneInfo(tz_str)
dt_from = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=0,  minute=0,  tzinfo=tz).astimezone(utc)
dt_to   = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz).astimezone(utc)
```

### "Today" / "Tomorrow" in local time
```python
def _resolve_date(value: str, tz_str: str = "UTC") -> str:
    from zoneinfo import ZoneInfo
    v = value.lower()
    if v in ("today", "tomorrow"):
        now_local = datetime.now(ZoneInfo(tz_str))
        if v == "tomorrow":
            now_local += timedelta(days=1)
        return now_local.date().isoformat()
    return value
```

### Working hours check — convert to local before comparing
```python
local_dt = dt.astimezone(ZoneInfo(tenant.timezone or "UTC"))
if not (tenant.open_hour <= local_dt.hour < tenant.close_hour):
    return False  # outside working hours
```

Without this, a Moscow salon (UTC+3) with `open_hour=10` would reject bookings at 10:00–12:00 because UTC hour (7–9) is less than 10.

---

## Google Calendar Integration

### Architecture

Platform has ONE service account. Each tenant shares their own Google Calendar with it. The bot uses that shared calendar as the source of truth.

```
GOOGLE_CALENDAR_CREDENTIALS = full JSON of service account key
tenant.google_cal_id         = calendar ID provided by salon owner
```

### Adapter factory — cache per tenant, fall back to local DB
```python
def get_adapter(tenant) -> BookingAdapter:
    if tenant.id not in _adapters:
        creds_json = tenant.google_cal_credentials or settings.GOOGLE_CALENDAR_CREDENTIALS
        if creds_json and tenant.google_cal_id:
            try:
                _adapters[tenant.id] = GoogleAdapter(tenant, creds_json)
            except Exception:
                _adapters[tenant.id] = LocalAdapter(tenant)  # silent fallback
        else:
            _adapters[tenant.id] = LocalAdapter(tenant)
    return _adapters[tenant.id]
```

Call `invalidate_adapter(tenant_id)` + `TenantMiddleware.invalidate(token)` any time the tenant's GCal config changes.

### System prompt must check PLATFORM credentials too

**Wrong — always shows "local storage only" for platform-cred tenants:**
```python
if tenant.google_cal_credentials and tenant.google_cal_id:
    calendar_line = "Google Calendar synced"
```

**Correct:**
```python
from aria.config import settings
has_creds = bool(tenant.google_cal_credentials or settings.GOOGLE_CALENDAR_CREDENTIALS)
if has_creds and tenant.google_cal_id:
    calendar_line = "Google Calendar synced"
```

### Tell the AI whether a booking went to GCal
```python
bid, cal_id = await adapter.create_event(...)
return json.dumps({
    "booking_id": bid,
    ...
    "google_calendar": cal_id is not None,  # MUST be in tool result
})
```

System prompt rule:
```
NEVER say a booking was saved to Google Calendar unless the tool result
contains "google_calendar": true.
```

### GCal events — use tenant timezone in the body
```python
body = {
    "start": {"dateTime": dt.isoformat(), "timeZone": tenant.timezone or "UTC"},
    "end":   {"dateTime": end_dt.isoformat(), "timeZone": tenant.timezone or "UTC"},
}
```

`dt` is already UTC (`+00:00`). Google Calendar uses the explicit offset from `dateTime` for the actual time, and `timeZone` for display. Sending both ensures the event shows at the correct local time in the owner's calendar.

### Extract calendar ID from any URL format
Users paste iCal links instead of bare IDs. Extract with:
```python
import re
from urllib.parse import unquote

def _extract_cal_id(text: str) -> str:
    m = re.search(r"/calendar/(?:ical|r)/([^/\s]+)/", text)
    if m:
        return unquote(m.group(1))
    m = re.search(r"[?&]cid=([^&\s]+)", text)
    if m:
        return unquote(m.group(1))
    return text.strip()
```

---

## AI / Claude Integration

### Use prompt caching on the system prompt
```python
response = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system=[{"type": "text", "text": system_prompt,
             "cache_control": {"type": "ephemeral"}}],
    tools=TOOLS,
    messages=history,
    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
```

### Tool loop — cap at MAX_TOOL_ROUNDS
```python
for _ in range(MAX_TOOL_ROUNDS):  # e.g. 5
    response = await client.messages.create(...)
    if not tool_calls:
        break
    # execute tools, append results, continue
else:
    text_reply = "Something went wrong, please try again."
```

### Map GCal exceptions to actionable messages
```python
except Exception as exc:
    if "404" in str(exc) or "Not Found" in str(exc):
        result = json.dumps({"error": "calendar_not_found",
                             "hint": "Share the calendar with the service account (Editor role)."})
    elif "403" in str(exc) or "disabled" in str(exc):
        result = json.dumps({"error": "calendar_api_disabled",
                             "hint": "Enable Google Calendar API in Google Cloud Console."})
    else:
        result = json.dumps({"error": str(exc)})
```

---

## Database

Use `asyncpg` with a connection pool. Raw SQL only — no ORM.

```python
_pool: asyncpg.Pool | None = None

async def get_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    return _pool
```

Schema uses `IF NOT EXISTS` everywhere so it is safe to run on both fresh and existing databases. Migrations are `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` appended to the schema string — no migration tooling needed.

`TIMESTAMPTZ` columns: asyncpg returns them as timezone-aware Python `datetime` in UTC. Always store and compare in UTC. Convert to local only for display.

---

## Setup Wizard (FSM)

States: `salon_name → owner_name → services → hours → timezone → google_cal`

Key rules:
- After setup completes: call `invalidate_adapter()`, `TenantMiddleware.invalidate()`, `set_commands()` (to register owner menu commands), then send the success message.
- `owner_tg_id` is saved at the START of the wizard (on `/start`), not at the end. Otherwise if the wizard is abandoned, you don't know who started it.
- Timezone step uses inline keyboard + free-text fallback validated with `zoneinfo.ZoneInfo(tz)`.

---

## Bot Command Menu

Register commands with `set_my_commands`. Two scopes:
- `BotCommandScopeDefault()` — basic commands for all users
- `BotCommandScopeChat(chat_id=owner_tg_id)` — extended commands for the salon owner

Call `set_commands(bot, owner_tg_id)` in two places:
1. `_poll_bot` after startup (for already-configured tenants)
2. At the end of the setup wizard (for newly configured tenants)

---

## Railway Deployment

- All secrets in Railway Variables, never in code or `.env` committed to git
- `GOOGLE_CALENDAR_CREDENTIALS` — paste the entire JSON content of the service account key file as a single-line value
- The tenant watcher loop (`_watch_tenants`) polls the DB every 10 seconds and starts polling tasks for new tenants automatically — no restart needed when adding a new bot
- `TelegramConflictError` on deploy is normal — old container is still running when new one starts. Self-resolves within ~30 seconds.

---

## Checklist Before Deploy

- [ ] `GOOGLE_CALENDAR_CREDENTIALS` contains valid JSON (not a file path)
- [ ] Google Calendar API enabled in Cloud Console
- [ ] `BOT_TOKEN` set in Railway Variables
- [ ] `DATABASE_URL` set in Railway Variables
- [ ] `ANTHROPIC_API_KEY` set in Railway Variables
- [ ] `ADMIN_TELEGRAM_ID` and `OWNER_TELEGRAM_ID` set correctly
- [ ] Schema has `ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC'`
- [ ] Routers included in correct order (setup → admin → start → chat)
- [ ] `chat.router` is the last included router (catch-all)
- [ ] Filters use `**kwargs` not typed DI
- [ ] Multi-bot polling uses `dp.feed_update()` not `dp.start_polling()`
