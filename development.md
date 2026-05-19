# Aria — Multi-Tenant Salon Bot Platform
## Complete Development Reference

This document contains the full architecture, every file with its exact purpose and key code, all bugs that were encountered and fixed, and complete rebuild instructions. If this project is ever lost, hand this document to Claude Code and say: **"Rebuild the Aria multi-tenant salon bot platform exactly as described in this development.md."**

---

## Table of Contents

1. [What Aria Does](#1-what-aria-does)
2. [Architecture Overview](#2-architecture-overview)
3. [Project File Tree](#3-project-file-tree)
4. [Environment Variables](#4-environment-variables)
5. [Database Schema](#5-database-schema)
6. [File-by-File Reference](#6-file-by-file-reference)
7. [Critical Bugs Found and Fixed](#7-critical-bugs-found-and-fixed)
8. [Railway Deployment](#8-railway-deployment)
9. [How Each Feature Works](#9-how-each-feature-works)
10. [Rebuild Instructions for Claude Code](#10-rebuild-instructions-for-claude-code)

---

## 1. What Aria Does

Aria is a **multi-tenant Telegram bot platform** for beauty salons. One Railway deployment runs N salon bots simultaneously. Each salon gets its own Telegram bot token; each bot has its own isolated data (bookings, clients, calendar, email).

**Owner features (salon owner talks to their bot):**
- AI assistant (Claude Haiku) that understands natural Russian: "запиши Катю на ресницы 20 мая в 14:00"
- Guided booking wizard via inline keyboard (no AI tokens needed)
- Google Calendar sync — bookings created directly in GCal
- Email monitoring — IMAP inbox forwarded to Telegram every 5 min
- Schedule views: today, tomorrow, upcoming, week
- Settings panel: timezone, calendar ID, email, service catalogue
- Reminder notifications (day before) and no-show checks (2 hours after)
- VIP client tags, reactivation alerts for inactive clients

**Platform admin features (via @AriaReseptionist_Bot):**
- List all active bots
- Add a new bot (just send a token — bot starts within 60 seconds)
- Broadcast messages to all salon owners
- Assign/revoke VIP status per tenant
- Reset a bot's setup, deactivate bots

**Client features (salon clients talking to the bot):**
- The bot is not designed for direct client interaction — it's an owner-facing tool

---

## 2. Architecture Overview

```
Railway (single process)
│
├── main.py — entry point
│   ├── init_db() — runs SCHEMA migrations on startup
│   ├── _ensure_initial_tenant() — seeds first tenant from env vars
│   ├── _build_dispatcher() — ONE shared aiogram Dispatcher
│   │   └── TenantMiddleware — resolves TenantConfig from bot token (30s cache)
│   │   └── Routers: setup → admin → start → menu → quick → email_setup → chat
│   ├── _poll_bot(bot, dp, tenant_id) — long-polling loop per bot
│   │   └── bot.get_updates() → dp.feed_update() → handler
│   └── _watch_tenants(dp) — every 10s: start/stop bots as DB changes
│
├── PostgreSQL — all state
│   ├── aria_tenants — one row per bot (token, config, GCal, email)
│   ├── aria_bookings — appointments with GCal event ID
│   ├── aria_clients — CRM: style, VIP status
│   ├── aria_conversations — Claude conversation history (JSONB)
│   ├── aria_fsm_states — aiogram FSM states (survive restarts)
│   ├── aria_service_categories / aria_service_items — service catalogue
│   └── aria_waitlist — waitlist entries
│
├── APScheduler (AsyncIOScheduler)
│   ├── Reminder jobs — 09:00 local day before each booking
│   ├── No-show jobs — 2h after each booking
│   ├── Email poll jobs — every 5 min per tenant with email configured
│   └── Daily reactivation — 10:00 UTC, notifies about 45-day inactive clients
│
└── External APIs
    ├── Anthropic (Claude Haiku 4.5) — AI chat with tool use
    └── Google Calendar API — via service account, per-platform credentials
```

### Key Design Decisions

**Single Dispatcher, multiple bots.** All bots share one `Dispatcher` instance. `dp.feed_update(bot, update)` routes each update with the correct bot object injected. This avoids duplicating router registration.

**TenantMiddleware.** Every update goes through `TenantMiddleware` which looks up the tenant by `bot.token`, caches it 30 seconds, and injects `data["tenant"]` into all handlers. Handlers receive `tenant: TenantConfig` via aiogram's dependency injection.

**Router order is critical.** `setup_router` must be first (handles `/start` when `setup_complete=False`). `chat.router` must be last (catch-all `@router.message()` with no filters).

**PostgresFSMStorage.** FSM states are stored in Postgres so wizard progress survives bot restarts and Railway redeploys. The critical invariant: must store `state.state` (the string `"Group:name"`) NOT `str(state)` (which gives `"<State 'Group:name'>"` with angle brackets that never match `StateFilter`).

**BookingAdapter pattern.** `LocalAdapter` stores everything in Postgres. `GoogleAdapter` stores in both GCal and Postgres. Factory `get_adapter(tenant)` picks the right one based on whether `google_cal_id` and credentials are set. Both adapters have the same interface.

---

## 3. Project File Tree

```
Self-AwarnessBot/
├── development.md              ← this file
├── requirements.txt            ← root-level (legacy, not used by Railway)
├── railway.toml                ← root-level (legacy)
│
└── aria/                       ← THE actual application
    ├── __init__.py             ← empty
    ├── main.py                 ← entry point, polling engine, tenant watcher
    ├── config.py               ← Settings class, reads env vars
    ├── tenant.py               ← TenantConfig dataclass
    ├── middleware.py           ← TenantMiddleware (resolves tenant per update)
    ├── filters.py              ← SetupRequired / SetupDone filters
    ├── runtime.py              ← shared bots dict {tenant_id: Bot}
    ├── railway.toml            ← Railway build/deploy config (USED)
    ├── requirements.txt        ← Python dependencies (USED)
    ├── Dockerfile              ← Docker config (alternative to nixpacks)
    ├── .env.example            ← documentation of all env vars
    │
    ├── db/
    │   ├── __init__.py
    │   ├── models.py           ← SCHEMA SQL string (CREATE TABLE + migrations)
    │   ├── repo.py             ← all database queries (asyncpg)
    │   └── fsm_storage.py      ← PostgresFSMStorage for aiogram FSM
    │
    ├── handlers/
    │   ├── __init__.py
    │   ├── setup.py            ← Setup wizard (runs when setup_complete=False)
    │   ├── admin.py            ← Admin commands, broadcast, service catalogue FSM
    │   ├── start.py            ← /start, /help, /reset, /set_cal, /set_tz, /status
    │   ├── menu.py             ← Inline settings panel, schedule callbacks
    │   ├── quick.py            ← Reply keyboard shortcuts, guided booking wizard
    │   ├── email_setup.py      ← Email configuration wizard
    │   └── chat.py             ← Catch-all → AI service (MUST be last router)
    │
    └── services/
        ├── __init__.py
        ├── ai.py               ← Claude chat with tool use
        ├── booking.py          ← LocalAdapter + GoogleAdapter
        ├── commands.py         ← set_my_commands per bot
        ├── email_monitor.py    ← IMAP polling, forwarding to Telegram
        ├── scheduler.py        ← APScheduler jobs (reminders, no-show, reactivation)
        └── voice.py            ← [S1] OpenAI Whisper transcription
```

---

## 4. Environment Variables

Set these in **Railway → Variables**:

### Required

| Variable | Description |
|---|---|
| `ARIA_BOT_TOKEN` | First salon bot token from @BotFather. Seeds the initial tenant. Also accepted as `BOT_TOKEN` (legacy). |
| `ANTHROPIC_API_KEY` | Anthropic API key. Also accepted as `CLAUDE_API_KEY` (legacy). |
| `ARIA_OWNER_TELEGRAM_ID` | Your personal Telegram numeric ID (admin). Also accepted as `OWNER_ID` (legacy). |
| `DATABASE_URL` | PostgreSQL connection string. Also accepted as `ARIA_DATABASE_URL`. |

### Initial Tenant Setup (read once at first startup)

| Variable | Default | Description |
|---|---|---|
| `SALON_NAME` | `My Salon` | Salon display name |
| `SALON_OWNER_NAME` | `Owner` | Owner's first name |
| `SALON_SERVICES` | `haircut, manicure` | Comma-separated service list |
| `SALON_HOURS` | `Mon-Sat 10:00-20:00` | Display string for AI |
| `SALON_OPEN_HOUR` | `10` | Opening hour (int) |
| `SALON_CLOSE_HOUR` | `20` | Closing hour (int) |
| `SALON_SLOT_MINUTES` | `60` | Slot duration in minutes |
| `SALON_WORKING_DAYS` | `1,2,3,4,5,6` | ISO weekdays (1=Mon…7=Sun) |

### Optional

| Variable | Description |
|---|---|
| `MANAGEMENT_BOT_TOKEN` | Token of the admin management bot (@AriaReseptionist_Bot). That bot shows the admin panel UI instead of the salon UI. |
| `OPENAI_API_KEY` | **[S1]** OpenAI API key for Whisper voice transcription. If not set, voice messages are rejected with `voice_error` i18n message. |
| `GOOGLE_CALENDAR_CREDENTIALS` | Full service account JSON as a single-line string. Platform-wide; all tenants share this service account. |
| `GOOGLE_CALENDAR_ID` | Default calendar ID (can be set per-tenant via /set_cal). |

### Notes on env var naming
`config.py` accepts both old and new names to avoid breaking existing deployments:
```python
self.BOT_TOKEN = _str("ARIA_BOT_TOKEN") or _str("BOT_TOKEN", "")
self.ANTHROPIC_API_KEY = _str("ANTHROPIC_API_KEY") or _str("CLAUDE_API_KEY", "")
self.ADMIN_TELEGRAM_ID = _int("ARIA_OWNER_TELEGRAM_ID", 0) or _int("OWNER_ID", 0)
```

---

## 5. Database Schema

All tables use `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` so the schema is idempotent — safe to re-run on every startup.

### `aria_tenants`
One row per bot. Central config table.
```sql
id                     SERIAL PRIMARY KEY
bot_token              TEXT UNIQUE NOT NULL
owner_tg_id            BIGINT                    -- Telegram ID of salon owner
salon_name             TEXT NOT NULL DEFAULT 'My Salon'
owner_name             TEXT NOT NULL DEFAULT 'Owner'
services               TEXT NOT NULL DEFAULT 'haircut, manicure'
hours                  TEXT NOT NULL DEFAULT 'Mon-Sat 10:00-20:00'
open_hour              INT  NOT NULL DEFAULT 10
close_hour             INT  NOT NULL DEFAULT 20
slot_minutes           INT  NOT NULL DEFAULT 60
working_days           TEXT NOT NULL DEFAULT '1,2,3,4,5,6'
google_cal_credentials TEXT                      -- per-tenant service account JSON (optional)
google_cal_id          TEXT                      -- GCal calendar ID (set via /set_cal)
anthropic_api_key      TEXT                      -- per-tenant API key override (optional)
setup_complete         BOOLEAN NOT NULL DEFAULT FALSE
active                 BOOLEAN NOT NULL DEFAULT TRUE
timezone               TEXT NOT NULL DEFAULT 'UTC'   -- IANA tz name, e.g. Europe/Moscow
email_host             TEXT
email_port             INT  NOT NULL DEFAULT 993
email_user             TEXT
email_password         TEXT
email_folder           TEXT NOT NULL DEFAULT 'INBOX'
email_last_uid         TEXT                      -- highest fetched IMAP UID
email_filter_type      TEXT NOT NULL DEFAULT 'all'  -- 'all'|'keywords'|'senders'
email_filter_value     TEXT
created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### `aria_bookings`
```sql
id                  BIGSERIAL PRIMARY KEY
tenant_id           INT     NOT NULL DEFAULT 1
user_id             BIGINT  NOT NULL              -- Telegram ID of booking creator
client_name         TEXT    NOT NULL
service             TEXT    NOT NULL
scheduled_at        TIMESTAMPTZ NOT NULL
status              TEXT    NOT NULL DEFAULT 'confirmed'  -- 'confirmed'|'cancelled'|'pending'
reminder_sent       BOOLEAN NOT NULL DEFAULT FALSE
noshow_check_sent   BOOLEAN NOT NULL DEFAULT FALSE
upsell_offered      BOOLEAN NOT NULL DEFAULT FALSE
calendar_event_id   TEXT                          -- GCal event ID (null for local-only)
created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Index: `(tenant_id, scheduled_at) WHERE status = 'confirmed'`

### `aria_clients`
```sql
tenant_id           INT     NOT NULL DEFAULT 1
user_id             BIGINT  NOT NULL
lang                TEXT    NOT NULL DEFAULT 'en'
communication_style TEXT    NOT NULL DEFAULT 'casual'  -- 'casual'|'formal'|'terse'
is_vip              BOOLEAN NOT NULL DEFAULT FALSE
vip_until           TIMESTAMPTZ
reactivation_sent   BOOLEAN NOT NULL DEFAULT FALSE
notes               TEXT
created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
PRIMARY KEY (tenant_id, user_id)
```

### `aria_conversations`
```sql
tenant_id   INT     NOT NULL DEFAULT 1
user_id     BIGINT  NOT NULL
history     JSONB   NOT NULL DEFAULT '[]'     -- list of Claude message dicts
updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
PRIMARY KEY (tenant_id, user_id)
```

### `aria_fsm_states`
```sql
key   TEXT PRIMARY KEY    -- "bot_id:chat_id:user_id:destiny"
state TEXT                -- "StatesGroup:state_name" (NO angle brackets)
data  JSONB NOT NULL DEFAULT '{}'
```

### `aria_service_categories`
```sql
id        SERIAL PRIMARY KEY
tenant_id INT  NOT NULL DEFAULT 1
name      TEXT NOT NULL
position  INT  NOT NULL DEFAULT 0
UNIQUE (tenant_id, name)
```

### `aria_service_items`
```sql
id          SERIAL PRIMARY KEY
category_id INT  NOT NULL REFERENCES aria_service_categories(id) ON DELETE CASCADE
name        TEXT NOT NULL
position    INT  NOT NULL DEFAULT 0
UNIQUE (category_id, name)
```

### `aria_waitlist`
```sql
id          BIGSERIAL PRIMARY KEY
tenant_id   INT     NOT NULL DEFAULT 1
user_id     BIGINT  NOT NULL
client_name TEXT    NOT NULL
service     TEXT    NOT NULL
notified    BOOLEAN NOT NULL DEFAULT FALSE
added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

---

## 6. File-by-File Reference

### `aria/requirements.txt`
```
flask==3.0.3
gunicorn==21.2.0
anthropic>=0.40.0
aiogram==3.13.1
asyncpg>=0.29.0
apscheduler>=3.10.0
requests>=2.31.0
google-auth>=2.0.0
google-api-python-client>=2.0.0
tzdata>=2024.1
openai>=1.30.0       # [S1] Whisper voice transcription
```

### `aria/railway.toml`
```toml
[build]
builder = "nixpacks"
buildCommand = "pip install -r aria/requirements.txt"

[deploy]
startCommand = "python -m aria.main"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

### `aria/runtime.py`
Shared mutable state — `bots` dict populated by `main.py`, read by broadcast handlers.
```python
bots: dict[int, "Bot"] = {}   # tenant_id → Bot instance
```

### `aria/config.py`
Reads env vars at startup. No `_require()` calls — missing vars are caught lazily in `main()`.
Key: accepts both old (`BOT_TOKEN`, `OWNER_ID`) and new (`ARIA_BOT_TOKEN`, `ARIA_OWNER_TELEGRAM_ID`) names.

### `aria/tenant.py`
`TenantConfig` dataclass. Loaded from DB row via `TenantConfig.from_record(dict(row))`.
Key properties:
- `effective_api_key` — per-tenant `anthropic_api_key` or platform fallback
- `working_days_list` — parses `"1,2,3,4,5,6"` → `[1, 2, 3, 4, 5, 6]`
- `is_owner(user_id)` — checks if user matches `owner_tg_id`

### `aria/middleware.py`
`TenantMiddleware` — resolves `TenantConfig` from `bot.token` on every update.
- Cache TTL: 30 seconds (in-memory dict `{token: (TenantConfig, timestamp)}`)
- **[S1]** `_last_good: dict[str, TenantConfig]` — permanent fallback dict. On DB error when cache is empty, uses last known good TenantConfig instead of returning `None`. Prevents voice and text messages from being silently dropped after a transient DB hiccup.
- Always sets `data["tenant"] = None` when not found (prevents DI crash)
- `TenantMiddleware.invalidate(bot_token)` — call after any tenant config change

### `aria/filters.py`
Two filters using `**kwargs` pattern (required in aiogram 3 for DI):
```python
class SetupRequired(BaseFilter):
    async def __call__(self, message: Message, **kwargs) -> bool:
        tenant = kwargs.get("tenant")
        return tenant is not None and not tenant.setup_complete

class SetupDone(BaseFilter):
    async def __call__(self, message: Message, **kwargs) -> bool:
        tenant = kwargs.get("tenant")
        return tenant is not None and tenant.setup_complete
```
**Critical:** must use `**kwargs` not typed parameter `tenant: TenantConfig` — typed params return `None` in `BaseFilter.__call__`.

### `aria/db/fsm_storage.py`
PostgreSQL-backed FSM storage. Key invariant in `set_state`:
```python
if state is None:
    state_str = None
elif hasattr(state, "state"):
    state_str = state.state   # "Group:name" — NO angle brackets
else:
    state_str = str(state)
```
**Never use `str(state)`** — aiogram 3 gives `"<State 'Group:name'>"` which never matches `StateFilter`.

### `aria/db/models.py`
Single `SCHEMA` string. Applied on every startup via `conn.execute(SCHEMA)`.
All statements are idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
Includes PK migration scripts for tables that had old single-column PKs.

### `aria/db/repo.py`
All asyncpg queries. Key functions:
- `init_db(dsn)` — creates pool, runs schema
- `get_tenant_by_token(token)` — used by middleware
- `create_tenant(...)` — upserts on conflict (bot_token unique)
- `update_tenant(id, **fields)` — dynamic UPDATE for any fields
- `get_bookings_in_range(tenant_id, date_from, date_to)` — returns bookings for date range
- `load_history / save_history` — conversation history as JSONB
- `list_active_owner_bots()` — for broadcast and reactivation

**Critical: only ONE definition of `get_bookings_in_range`.** Signature is `(tenant_id: int, date_from: datetime, date_to: datetime)`. If accidentally duplicated with a 2-arg version, every call crashes with `TypeError`.

### `aria/main.py`
Entry point. Key flow:
1. Check `settings.BOT_TOKEN` and `settings.ANTHROPIC_API_KEY` — log critical and return if missing
2. `init_db()` → `_ensure_initial_tenant()` → `get_scheduler().start()`
3. `_build_dispatcher()` — creates ONE shared Dispatcher with `PostgresFSMStorage()`
4. Start polling tasks for all active tenants
5. `_watch_tenants(dp)` — infinite loop, every 10s checks DB for new/removed tenants

Router registration order (important — must be exactly this):
```python
dp.include_router(setup_router)    # 1. Setup wizard (SetupRequired filter)
dp.include_router(admin.router)    # 2. Admin commands
dp.include_router(start.router)    # 3. /start with SetupDone, owner settings
dp.include_router(menu.router)     # 4. Inline menu callbacks
dp.include_router(quick.router)    # 5. Reply keyboard, booking wizard
dp.include_router(email_setup.router)  # 6. Email setup wizard
dp.include_router(chat.router)     # 7. Catch-all (NO filter) — MUST BE LAST
```

### `aria/handlers/setup.py`
Setup wizard for new tenants (`setup_complete=False`).
FSM: `Setup.salon_name → owner_name → services → hours → timezone → google_cal`
- Triggered by `/start` + `SetupRequired()` filter
- Timezone step shows inline keyboard with 8 timezone options or accepts free text
- On completion: `update_tenant(setup_complete=True)`, `invalidate_adapter()`, `set_commands()`
- `/ping` command — debug: shows tenant info

### `aria/handlers/admin.py`
Platform admin + service catalogue.
FSM groups:
- `AddBot.waiting_token` — triggered by `➕ Добавить бота` or `/add_bot`
- `AdminBroadcast.waiting_text` — triggered by `📣 Рассылка`
- `CatalogueSG.add_category` / `add_item` — triggered by inline catalogue buttons

Admin commands (only work for `ADMIN_TELEGRAM_ID`):
- `/add_bot` — add new tenant bot
- `/list_bots` — list all active tenants
- `/reset_bot <id>` — reset setup, owner must redo wizard
- `/deactivate_bot <id>` — deactivate tenant
- `/broadcast <text>` — one-shot broadcast
- `/set_vip <tid> <uid> [days]` — grant VIP
- `/revoke_vip <tid> <uid>` — revoke VIP
- `/cancel` — clears any FSM state

Service catalogue callbacks (all require `SetupDone()`):
- `adm:services` — show categories list
- `adm:addcat` — prompt for new category name
- `adm:cat:<id>` — show items in category
- `adm:addsub:<cat_id>` — prompt for new item name
- `adm:dcat:<id>` / `adm:dsub:<id>:<cat_id>` — delete category/item
- `adm:main` — back to main admin/settings panel

### `aria/handlers/start.py`
Owner-facing commands after setup.
FSM groups:
- `OwnerSettings.waiting_cal_id` — triggered by `/set_cal` or `cfg:cal` button
- `OwnerSettings.waiting_tz` — triggered by `/set_tz` or `cfg:tz` button

Commands:
- `/start` + `SetupDone()` — greets owner, shows MAIN_KB or ADMIN_KB
- `/reset` — clear conversation history
- `/help` — command list with owner extras
- `/status` — GCal + email status display
- `/set_cal` — enter GCal calendar ID (extracts ID from full URLs too)
- `/set_tz` — change timezone (inline keyboard + free text)
- `/test_cal` — live GCal API diagnostic

`_extract_cal_id(text)` — handles raw IDs, iCal URLs (`/calendar/ical/ENCODED/`), and HTML URLs (`?cid=ENCODED`).

### `aria/handlers/menu.py`
Inline settings panel and schedule callbacks.
Two keyboard variants:
- `_owner_settings_kb()` — for salon owner bots (no Back button)
- `_admin_settings_kb()` — for admin bot (has Back → admin panel)
- `_admin_inline_kb()` — main admin panel for @AriaReseptionist_Bot

`_is_admin_bot(tenant, user_id)` — True when user is `ADMIN_TELEGRAM_ID` AND the bot token matches `MANAGEMENT_BOT_TOKEN`.

Callbacks handled:
- `menu:main`, `menu:settings`, `menu:close`
- `cfg:tz`, `cfg:cal`, `cfg:email`, `cfg:test_cal`, `cfg:reset_chat`, `cfg:status`
- `menu_tz:<tz>` — timezone selection from inline keyboard
- `sched:today`, `sched:tomorrow`, `sched:week`, `sched:next_week`, `sched:upcoming`
- `adm:list`, `adm:add`, `adm:broadcast`, `adm:vip_help`, `adm:revoke_help`

### `aria/handlers/quick.py`
Reply keyboard shortcuts and guided booking wizard.

Reply keyboard `MAIN_KB`:
```
📅 Сегодня | 📅 Завтра
➕ Новая запись | 📋 Ближайшие
📧 Почта | 📱 Меню
```

Schedule display helpers:
- `_show_schedule(message, tenant, days_offset)` — today/tomorrow view with cancel buttons
- `quick_upcoming(message, tenant)` — next 30 days
- `_delete_old_info(bot, chat_id)` — deletes previous schedule message before sending new

Guided booking wizard FSM: `QuickBook.service → date → time → client`
- All inline keyboard driven
- User text input during wizard: message is deleted, wizard message is edited in-place
- `wizard_msg_id` stored in FSM data to find the wizard message for editing
- Custom date: accepts `DD.MM`, `DD.MM.YYYY`, `YYYY-MM-DD`, `DD/MM`
- Custom time: accepts `HH:MM`
- On completion: creates booking via adapter, schedules reminder + no-show jobs

Cancel booking:
- `del_booking:<id>` callback on schedule/upcoming views
- Updates DB status to `cancelled`, calls `adapter.delete_event()`, cancels scheduler jobs

### `aria/handlers/email_setup.py`
IMAP email setup wizard.
FSM groups:
- `EmailSetup.address → host → password` — setup flow
- `EmailFilter.value` — filter value entry

IMAP server autodetection for: Gmail, Googlemail, Yandex, Mail.ru, Outlook, iCloud.

**Security:** `step_password` immediately calls `await message.delete()` after reading the password — passwords are never left in Telegram chat history.

Filter types:
- `all` — forward everything
- `keywords` — match subject/body against comma-separated keywords
- `senders` — match sender against comma-separated addresses/domains
- `service` — preset: picks from `_BOOKING_SERVICES` list (Yclients, Dikidi, Booksy, etc.)

### `aria/handlers/chat.py`
Catch-all handler — LAST router, no filters on `@router.message()`.

**[S1] Voice branch** (runs before text branch):
1. Check `message.voice` → transcribe via `aria.services.voice.transcribe(bot, file_id, lang)`
2. If transcription fails → `t("voice_error", lang)`
3. Echo `🎙 <i>«transcript»</i>` built but NOT sent standalone
4. Run `_schedule_bypass(message, tenant, override_text=user_text)` with transcribed text
5. If bypass hits → send echo alone, return
6. Otherwise → call `chat()` AI service → send `f"{echo}\n\n{reply}"` as one message
7. If FSM state is active → cleared before voice processing (voice always goes to AI)

Rule-based bypass (no AI tokens):
- "сегодня" / "завтра" (≤6 words, no booking verbs) → `_show_schedule`
- "ближайш" → `quick_upcoming`
- "следующая неделя" → `_show_week(offset=1)`
- "эта неделя" → `_show_week(offset=0)`

`_BOOKING_VERBS` (bypass is blocked when any of these appear in text):
```python
_BOOKING_VERBS = [
    "запис", "запиш",  # запись/записать + запиши/запишешь (разные морфемы!)
    "добавь", "добавить", "перенес", "отмен",
    "свободн", "проверь", "убери", "удали",
]
```
**[S1]** Added `"запиш"` — imperative "запиши" has root зап+ИШ, not зап+ИС.

FSM guard (text branch only):
```python
current_state = await state.get_state()
if current_state is not None:
    log.info("FSM state active (%s) but no handler matched — message: %r", ...)
    return
```
If FSM is active and no specific handler matched, silently drop (don't send to AI).

Rate limit: 20 messages per minute per user.

Style detection: detects "formal"/"terse"/"casual" and stores in DB. Passed to AI system prompt.

### `aria/services/ai.py`
Claude Haiku with tool use.

Model: `claude-haiku-4-5-20251001`  
Max tokens: 1024  
Max tool rounds: 5  
History limit: 40 messages (trimmed from oldest, preserving tool_use/tool_result pairs)

System prompt: embeds tenant config + style + TODAY date. Uses `cache_control: ephemeral` for prompt caching.

**[S1]** System prompt now includes "ЗАПИСЬ КЛИЕНТА" section:
```
— Из первого сообщения сразу извлеки всё доступное: имя клиента, услугу, дату, время
— Имя клиента часто стоит в начале: «Запиши Вику…» → client_name = «Вика»
— Уточняй только то, чего реально не хватает для add_booking — по одному вопросу
— Как только все 4 поля известны — немедленно вызывай add_booking, не переспрашивай
— Если клиент назван местоимением («её», «его») — ищи имя в предыдущих сообщениях
```

Tools (5):
- `get_schedule(date|date_from+date_to)` — list bookings for date/range
- `check_availability(date, time, service)` — is this slot free?
- `add_booking(client_name, service, date, time)` — create booking
- `reschedule_booking(booking_id, new_date, new_time)` — move booking
- `cancel_booking(booking_id)` — cancel (handles both int DB ID and string GCal ID)
- `get_upcoming(limit)` — next N bookings

AI rules in system prompt (enforced):
- If tool returns `"error"` field → booking NOT created, tell user
- Never claim GCal booking without `"google_calendar": true` in tool response
- If `"google_calendar": false` → tell owner it's saved only in bot

### `aria/services/voice.py` [S1 — NEW]
OpenAI Whisper voice transcription.

```python
async def transcribe(bot: "Bot", file_id: str, lang: str = "ru") -> Optional[str]:
```

Flow:
1. Check `settings.OPENAI_API_KEY` — return `None` if not set (disables feature)
2. `bot.get_file(file_id)` + `bot.download_file(...)` → `io.BytesIO` named `"voice.ogg"`
3. `openai.AsyncOpenAI(api_key=api_key).audio.transcriptions.create(model="whisper-1", ...)`
4. Return `result.text.strip()` or `None` if empty

Language map: `{"ru": "ru", "en": "en", "fi": "fi"}` — passed as `language` param to Whisper.

### `aria/services/booking.py`
Two adapter classes implementing `BookingAdapter` ABC.

**`LocalAdapter`:** everything in Postgres.
- `get_events(dt_from, dt_to)` → `repo.get_bookings_in_range(tenant_id, dt_from, dt_to)`
- `is_available(dt, service)` → checks working hours + `repo.get_slots_on_date`
- `create_event(...)` → `repo.create_booking(...)`, returns `(bid, None)`

**`GoogleAdapter`:** GCal as source of truth, Postgres as cross-reference.
- `__init__` — builds google-api-python-client service using service account JSON
- `get_events(dt_from, dt_to)` — `_list_events_sync` via GCal API, cross-refs with DB for integer IDs
- `is_available(dt, service)` — `_freebusy_sync` to check busy blocks
- `create_event(...)` — inserts to GCal, stores in DB with `calendar_event_id`. On GCal failure: saves to DB only, returns `(bid, None)` so AI knows `google_calendar: false`
- `update_event(...)` — updates DB time + GCal event via PATCH
- `delete_event(booking_id, cal_event_id)` — deletes from GCal only (caller updates DB status). Ignores 404/410 (already deleted)

**Critical: only ONE definition of each method.** If `delete_event` or `get_events` is accidentally defined twice in the class, Python keeps only the last one.

`get_adapter(tenant)` factory:
- Uses `tenant.google_cal_credentials` first, falls back to `settings.GOOGLE_CALENDAR_CREDENTIALS`
- Returns `GoogleAdapter` if both credentials and `google_cal_id` are set
- Otherwise returns `LocalAdapter`
- Caches in `_adapters` dict; `invalidate_adapter(tenant_id)` clears cache

### `aria/services/commands.py`
`set_commands(bot, owner_tg_id=None)` — sets bot commands via Telegram API.
- Default scope: `/start`, `/help`, `/reset`
- Owner scope (chat-specific): adds `/status`, `/connect_email`, `/test_cal`, `/set_cal`, `/set_tz`, `/cancel`

### `aria/services/email_monitor.py`
IMAP polling via `imaplib`. All IMAP calls are blocking, run via `asyncio.to_thread`.

`check_email(tenant_id, bot)`:
1. Read tenant config from DB
2. First poll: record current highest UID, return 0 (don't flood with old emails)
3. Subsequent polls: fetch emails with UID > last_uid (max 10 per poll)
4. Apply filter (`passes_filter`)
5. Forward matching emails to `owner_tg_id` as formatted Telegram messages
6. Advance `email_last_uid` to highest UID seen

Filter logic: `passes_filter(filter_type, filter_value, sender, subject, body)`
- `all` or no value → always pass
- `keywords` → any keyword in `(subject + body).lower()`
- `senders` → any term in `sender.lower()`

`detect_imap_host(email_addr)` — maps common domains to IMAP servers.

### `aria/services/scheduler.py`
APScheduler with `AsyncIOScheduler(timezone="UTC")`.

Jobs:
- `reminder_{booking_id}` — fires at 09:00 local time day before appointment
- `noshow_{booking_id}` — fires 2h after appointment time
- `waitlist_{id}` — fires in 1 second (immediate)
- `email_{tenant_id}` — fires every 5 minutes (IntervalTrigger)
- `daily_reactivation` — CronTrigger at 10:00 UTC

`schedule_reminder_job(booking_id, scheduled_at, owner_id, bot, tenant)`:
- Computes `remind_at = appointment_local_day - 1 day + 09:00`
- Skips if time already passed
- Uses `replace_existing=True` (safe to call on reschedule)

`cancel_booking_jobs(booking_id)` — removes both reminder and no-show jobs, ignores if not found.

---

## 7. Critical Bugs Found and Fixed

These bugs were ALL caused by the same pattern: **duplicate function/method definitions**. In Python, if a class or module defines the same name twice, the second definition silently overwrites the first. Every bug listed here caused the second (broken) definition to override the correct first one.

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
**Root cause:** Two definitions. First (correct): `(tenant_id: int, date_from: datetime, date_to: datetime)`. Second (broken override): `(date_from: "date", date_to: "date")` — no `tenant_id`, wrong types. Every caller passes 3 args → TypeError.  
**Fix:** Remove the second definition. Also remove the orphaned `get_bookings_by_gcal_ids` function that was only referenced by the now-removed duplicate `get_events`.

### Summary: How These Bugs All Came From One Source
All four bug groups were introduced during a code merge/refactor where old code from a previous version wasn't deleted when new versions were written. The new version was added BELOW the old one, and Python's name resolution meant the new (broken) version silently replaced the working old version. **Whenever refactoring, always delete the old definition before writing the new one, or search the file for duplicate names.**

---

## S1 Voice Feature Bugs (2026-05-19)

### Bug 5 — `~F.text.in_(set)` matches voice messages (text=None)
**Files:** `aria/handlers/quick.py`, `start.py`, `email_setup.py`, `menu.py`  
**Symptom:** Voice messages silently consumed by FSM step handlers. Log shows 19ms update processing. No response from bot.  
**Root cause:** Magic filter evaluation: `F.text.in_(frozenset(...)).resolve(msg)` = `False` when `msg.text is None`. Applying `~` negates it: `~False = True`. So FSM step handlers with filter `~F.text.in_(MAIN_KB_TEXTS)` matched voice messages (text=None) and crashed inside when doing `message.text.strip()`.  
**Fix:** Add explicit `F.text` as an additional filter on all FSM step handlers:
```python
# BROKEN — matches voice (text=None):
@router.message(QuickBook.date, ~F.text.in_(MAIN_KB_TEXTS))

# CORRECT — requires text to be non-None first:
@router.message(QuickBook.date, F.text, ~F.text.in_(MAIN_KB_TEXTS))
```
Applied to: `QuickBook.date/time/client`, `QuickEdit.note/reschedule`, `OwnerSettings.waiting_cal_id/waiting_tz`, `EmailFilter.value`, `EmailSetup.address/host/password`, `IncomeSettings.master_percent/tax_percent`.

### Bug 6 — Russian morphology: "запиши" not matched by "запис"
**File:** `aria/handlers/chat.py`, `_BOOKING_VERBS` list  
**Symptom:** "Запиши Вику на завтра" → shows tomorrow's schedule instead of starting a booking. Bypass incorrectly fired.  
**Root cause:** Russian morphology — "запиши" (imperative, record!) is зап+**ИШ**+и, while "запись"/"записать" (noun/infinitive) is зап+**ИС**+ь/ать. The substring `"запис"` is NOT in `"запиши"`. So `_has_booking_verb` returned False → bypass was not blocked → "завтра" in ≤6 word message → `_show_schedule` fired.  
**Fix:** Add `"запиш"` to booking verbs (catches imperative + future forms: запиши, запишешь, запишем):
```python
_BOOKING_VERBS = [
    "запис", "запиш",  # запись/записать + запиши/запишешь (разные морфемы)
    ...
]
```

### Bug 7 — TenantMiddleware returns `tenant=None` on DB cache miss
**File:** `aria/middleware.py`  
**Symptom:** After DB connection blip, all messages silently dropped for up to 30 seconds.  
**Root cause:** When cache TTL expired AND DB query failed, `cached` was still `None`. Code fell through to `tenant = cached[0] if cached else None` → `data["tenant"] = None`. Handler silently returned at `if not tenant or not tenant.setup_complete`.  
**Fix:** Added `_last_good: dict[str, TenantConfig]` permanent dict. On successful DB fetch, stores the config there. On DB error with empty cache, promotes last good config back to cache:
```python
_last_good: dict[str, TenantConfig] = {}

# On error:
if cached is None and bot.token in TenantMiddleware._last_good:
    fallback = TenantMiddleware._last_good[bot.token]
    TenantMiddleware._cache[bot.token] = (fallback, now)
    cached = TenantMiddleware._cache[bot.token]
```

---

## 8. Railway Deployment

### Initial Setup

1. Create a Railway project
2. Add a PostgreSQL plugin (Railway provides DATABASE_URL automatically)
3. Connect your GitHub repo
4. Set environment variables (see Section 4)
5. Push to `main` → Railway auto-deploys

### Build Configuration (`aria/railway.toml`)
```toml
[build]
builder = "nixpacks"
buildCommand = "pip install -r aria/requirements.txt"

[deploy]
startCommand = "python -m aria.main"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

The build command installs from `aria/requirements.txt` (not root `requirements.txt`). The start command runs `aria/main.py` as a module from the repo root.

### Deploy Flow
1. Push to `main` branch
2. Railway builds with nixpacks (Python 3.11)
3. `python -m aria.main` starts
4. `init_db()` creates/migrates all tables
5. `_ensure_initial_tenant()` seeds first bot from env vars (skips if already exists)
6. All 6+ bots start polling within seconds

### TelegramConflictError on deploy
During rolling deploy, old and new containers briefly overlap (5-10 seconds). Both try to poll the same bot → `TelegramConflictError`. This is expected and harmless — resolves automatically when the old container stops. Do not treat as a code bug.

### [S1] Auto-deploy from feature branch
Railway is configured to watch `claude/aria-voice-messages-7Jt8t` branch.  
Every `git push -u origin claude/aria-voice-messages-7Jt8t` triggers a deploy automatically.  
No manual redeploy needed; users don't need to press /start after a deploy.  
Stable snapshot: `stable/s1-voice` branch — checkout this to roll back.

### Adding a New Bot
1. Get a new token from @BotFather
2. In @AriaReseptionist_Bot, send `➕ Добавить бота` or `/add_bot`
3. Send the token
4. New tenant is created in DB with `setup_complete=False`
5. `_watch_tenants` picks it up within 10 seconds, starts polling
6. Tell the salon owner to open the bot and send `/start` — setup wizard runs

---

## 9. How Each Feature Works

### New Booking via AI
1. Owner types: "запиши Катю на ресницы 20 мая в 14:00"
2. `chat.py` → `_schedule_bypass` → no bypass (has booking verb)
3. `ai.py:chat()` → Claude Haiku gets message + history + system prompt
4. Claude calls `add_booking(client_name="Катя", service="ресницы", date="2026-05-20", time="14:00")`
5. `_exec_tool` → `parse_datetime("2026-05-20", "14:00", "Europe/Moscow")` → UTC datetime
6. `adapter.create_event(owner_id, "Катя", "ресницы", dt)`
   - If GCal: inserts to GCal API, stores in DB with `calendar_event_id`
   - If local: stores in DB only
7. Returns `{"booking_id": 42, "google_calendar": true/false, "confirmed": true}`
8. `schedule_reminder_job` + `schedule_noshow_job` scheduled
9. Claude receives tool result, generates confirmation message
10. Owner sees: "✅ Катя записана на ресницы 20 мая в 14:00 · Google Calendar 📅"

### New Booking via Wizard
1. Owner presses `➕ Новая запись`
2. `quick.py:quick_new` → `_start_booking` → sends inline keyboard with services
3. FSM state: `QuickBook.service`
4. Owner taps service → callback `qb_svc:Ресницы` → FSM → `QuickBook.date`
5. Owner taps date → `qb_date:2026-05-20` → FSM → `QuickBook.time`
6. Owner taps time → `qb_time:14:00` → FSM → `QuickBook.client`
7. Owner types "Катя" → `text_client` → creates booking via adapter
8. Message edited to show confirmation, FSM cleared

### Schedule View
1. Owner presses `📅 Сегодня`
2. `quick.py:quick_today` → `_show_schedule(message, tenant, 0)`
3. Computes UTC range for today in tenant timezone
4. `adapter.get_events(dt_from, dt_to)`
   - LocalAdapter: `repo.get_bookings_in_range(tenant_id, dt_from, dt_to)` → formats
   - GoogleAdapter: `_list_events_sync` via GCal API → cross-refs with DB for integer IDs
5. Builds text + inline keyboard with ❌ cancel buttons per booking
6. Deletes previous schedule message, sends new one

### Email Monitoring
1. Owner sets up email via `/connect_email`
2. `start_email_job(tenant_id, bot)` registers APScheduler IntervalTrigger every 5 min
3. Every 5 min: `check_email(tenant_id, bot)` runs
4. IMAP SSL connect → search UIDs > `email_last_uid` → fetch up to 10
5. Apply filter (all/keywords/senders)
6. Forward matching emails to owner as formatted Telegram messages
7. Update `email_last_uid` to highest seen

### Google Calendar Sync
1. Platform admin sets `GOOGLE_CALENDAR_CREDENTIALS` env var (service account JSON)
2. Each tenant sets their calendar ID via `/set_cal` or `cfg:cal` menu
3. Share the calendar with the service account email (Editor rights)
4. `get_adapter(tenant)` builds `GoogleAdapter` if both are set
5. `invalidate_adapter(tenant_id)` forces rebuild when config changes

---

## 10. Rebuild Instructions for Claude Code

If the project is lost, give this entire document to Claude Code with this prompt:

---

**REBUILD PROMPT:**

> Rebuild the Aria multi-tenant Telegram salon bot platform exactly as documented in this development.md. The project runs on Railway with Python 3.11, aiogram 3.13, asyncpg, APScheduler, and the Anthropic SDK.
>
> Key requirements:
> 1. One Railway process runs N bots simultaneously — one Dispatcher, multiple polling loops
> 2. PostgresFSMStorage must store `state.state` (not `str(state)`) — this is the #1 critical invariant
> 3. Each function/method must be defined exactly ONCE per file — the previous project had 4 groups of bugs all caused by duplicate definitions silently overriding correct ones
> 4. Router order: setup → admin → start → menu → quick → email_setup → chat (catch-all last)
> 5. Filters use `**kwargs` pattern (not typed `tenant: TenantConfig`) in `BaseFilter.__call__`
> 6. `data["tenant"] = None` when tenant not found in middleware — never leave it unset
> 7. Passwords typed by users must be deleted immediately with `await message.delete()`
> 8. `get_bookings_in_range` has exactly one definition with signature `(tenant_id, date_from, date_to)`
> 9. `GoogleAdapter` has exactly one `get_events` and one `delete_event` — both use `self._svc` and `self._cal`
>
> Create all files exactly as described in the File-by-File Reference section. Set up Railway deployment via `aria/railway.toml`. The start command is `python -m aria.main`.

---

### Environment variables to set in Railway after rebuild:

```
ARIA_BOT_TOKEN=<token from @BotFather for first salon bot>
ANTHROPIC_API_KEY=<Anthropic API key>
ARIA_OWNER_TELEGRAM_ID=<your Telegram numeric ID>
DATABASE_URL=<auto-provided by Railway PostgreSQL plugin>
MANAGEMENT_BOT_TOKEN=<token of @AriaReseptionist_Bot admin bot>
SALON_NAME=<first salon name>
SALON_OWNER_NAME=<first owner name>
GOOGLE_CALENDAR_CREDENTIALS=<service account JSON, single line>
```

### Verification checklist after deploy:
- [ ] Railway logs show "Aria polling mode — N bot(s)"
- [ ] No `RuntimeError` about env vars at startup
- [ ] `/ping` in any bot shows tenant info
- [ ] `/start` in a new (setup_complete=False) bot starts the wizard
- [ ] Wizard completes all 5 steps and sets setup_complete=True
- [ ] `📅 Сегодня` shows schedule (not TypeError)
- [ ] `➕ Новая запись` wizard works end-to-end
- [ ] `/set_cal` + Google Calendar URL → extracts ID correctly
- [ ] `/test_cal` shows "GCal API работает"
- [ ] New booking appears in GCal within seconds
- [ ] `/connect_email` → enters password → password message auto-deleted
- [ ] Email appears in Telegram within 5 minutes
- [ ] Admin bot `➕ Добавить бота` → new bot starts within 60 seconds
