# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

The production bot lives under `aria/`. All commands below assume you're in the repo root.

```bash
# Install dependencies
pip install -r aria/requirements.txt

# Run locally (requires env vars below)
cd aria && python -m aria.main

# One-off DB migration (runs automatically on startup via init_db)
# No separate migration runner — schema changes go into aria/db/models.py SCHEMA string
# New columns use ALTER TABLE ... ADD COLUMN IF NOT EXISTS at the bottom of SCHEMA
```

**Required env vars:**
- `ARIA_BOT_TOKEN` — main salon bot token (auto-seeds the initial tenant)
- `ANTHROPIC_API_KEY` — shared fallback; each tenant can override in the DB
- `ARIA_DATABASE_URL` or `DATABASE_URL` — PostgreSQL connection string
- `ARIA_OWNER_TELEGRAM_ID` — Telegram ID of the admin
- `MANAGEMENT_BOT_TOKEN` — token of @AriaReseptionist_Bot; omit if no admin bot

**Optional:**
- `GOOGLE_CALENDAR_CREDENTIALS` — JSON service account credentials
- `GOOGLE_CALENDAR_ID` — default GCal calendar ID for the initial tenant

Deployment: Railway auto-deploys from branch `claude/telegram-bots-project-1ArSJ` using `aria/Dockerfile` and `aria/railway.toml`.

## Architecture

### Multi-Tenant Polling

`aria/main.py` runs one `asyncio.Task` per active tenant (`_bots`, `_tasks` dicts). A watcher loop (`_watch_tenants`) polls `aria_tenants` every 10 s and starts/stops tasks as tenants are added or removed. All tenants share a single `Dispatcher` instance with one set of routers.

### TenantMiddleware (`aria/middleware.py`)

Resolves `TenantConfig` from the bot's token on every update. Uses a 30 s TTL in-memory cache keyed by bot token. Call `middleware.invalidate(bot_token)` to force a refresh (e.g. after setup changes). The resolved `TenantConfig` is injected into every handler as `tenant`.

### Two Bot Identities

- **Salon bots** (`BOT_TOKEN` and any tenant added via `/add_bot`): show owner management UI — booking wizard, schedule buttons, settings panel.
- **Admin bot** (`MANAGEMENT_BOT_TOKEN` → @AriaReseptionist_Bot): shows admin panel — list bots, add bot, broadcast.

`_is_admin_bot(tenant, user_id)` in `aria/handlers/menu.py` distinguishes them by comparing `tenant.bot_token == settings.MANAGEMENT_BOT_TOKEN`. Never use `ADMIN_TELEGRAM_ID` alone — it's the same value as `OWNER_TELEGRAM_ID`.

### Router Order (matters!)

```
setup_router → admin.router → start.router → menu.router → quick.router → email_setup.router → chat.router
```

`chat.router` is last — its catch-all `@router.message()` must not shadow setup/admin handlers.

### BookingAdapter Pattern (`aria/services/booking.py`)

`get_adapter(tenant)` returns:
- `GoogleAdapter` when tenant has `google_cal_credentials` + `google_cal_id` (or global GCal credentials)
- `LocalAdapter` otherwise (Postgres-only)

Always use `get_adapter(tenant)` — never instantiate adapters directly. Invalidate with `invalidate_adapter(tenant_id)` after credential changes.

### AI Service (`aria/services/ai.py`)

- Model: `claude-haiku-4-5-20251001` with tool use and prompt caching (`cache_control: ephemeral`)
- Up to `MAX_TOOL_ROUNDS = 5` agentic loops per message
- Conversation history stored in `aria_conversations` (JSONB). `_trim_history()` ensures the trimmed slice never starts mid tool_use/tool_result pair (would cause Anthropic API error)
- 6 tools: `get_schedule`, `check_availability`, `add_booking`, `reschedule_booking`, `cancel_booking`, `get_upcoming`

### Rule-Based Bypass (`aria/handlers/chat.py`)

Before calling AI, `_schedule_bypass()` intercepts simple schedule queries (today/tomorrow/upcoming/this week/next week) with zero token cost. Uses the same `get_adapter(tenant)` as button handlers so GCal sync is preserved. Returns early if any booking-mutation keyword is detected (`_BOOKING_VERBS`).

### Compact UI Patterns

**Booking wizard** (`aria/handlers/quick.py`): stores `wizard_msg_id` in FSM state; every step calls `edit_text` on the same message. Text inputs (`text_date`, `text_time`, `text_client`) delete the user's message then edit the wizard message.

**Schedule display** (`quick.py`): `_last_info_msg` dict (chat_id → message_id) tracks the last schedule message; `_delete_old_info()` removes it before sending a new one.

**Settings panel** (`aria/handlers/menu.py`): calendar/email/status buttons delete the inline menu and open a clean dialog. Timezone selection edits in-place.

**Important**: Settings callbacks that call `cmd_status` or `cmd_test_cal` must pass `caller_id=callback.from_user.id` — `callback.message.from_user` is the bot itself, not the owner.

### FSM Storage

`aria/db/fsm_storage.py` — custom `asyncpg`-backed FSM storage using `aria_fsm_states` table. This means FSM state survives restarts.

### Scheduler (`aria/services/scheduler.py`)

APScheduler `AsyncIOScheduler`. Key jobs:
- **Reminder**: fires at 09:00 local time the day before appointment
- **No-show check**: fires 2 h after appointment start
- **Daily reactivation**: 10:00 UTC, re-sends `/start` keyboard to all known owners

Cancel jobs with `cancel_booking_jobs(booking_id)` when a booking is cancelled or rescheduled.

### Database (`aria/db/`)

`models.py` holds the full schema as a string; `init_db()` runs it on startup. Schema changes: add `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` at the bottom — never drop the `CREATE TABLE` block. `repo.py` has all query functions; no ORM.

Key tables: `aria_tenants`, `aria_bookings`, `aria_clients`, `aria_conversations`, `aria_fsm_states`.

### Filters (`aria/filters.py`)

- `SetupDone` — passes only when `tenant.setup_complete` is True; used on all normal operation handlers
- `SetupRequired` — passes when setup is incomplete; used by `setup_router`

Always add the appropriate filter to new handlers. Missing filter → handler fires even before setup is finished.
