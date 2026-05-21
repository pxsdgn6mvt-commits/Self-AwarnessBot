# Aria — Project Overview for Architect

## What This Project Does

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

## Architecture Overview

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
│   └── _watch_tenants(dp) — every 10s: start/stop bots as DB changes
│
├── PostgreSQL — all state
└── External APIs: Anthropic (Claude Haiku 4.5), Google Calendar API
```

### Key Design Decisions

**Single Dispatcher, multiple bots.** All bots share one `Dispatcher` instance. `dp.feed_update(bot, update)` routes each update with the correct bot object injected. This avoids duplicating router registration.

**TenantMiddleware.** Every update goes through `TenantMiddleware` which looks up the tenant by `bot.token`, caches it 30 seconds, and injects `data["tenant"]` into all handlers. Handlers receive `tenant: TenantConfig` via aiogram's dependency injection.

**Router order is critical.** `setup_router` must be first (handles `/start` when `setup_complete=False`). `chat.router` must be last (catch-all `@router.message()` with no filters).

**PostgresFSMStorage.** FSM states are stored in Postgres so wizard progress survives bot restarts and Railway redeploys. The critical invariant: must store `state.state` (the string `"Group:name"`) NOT `str(state)` (which gives `"<State 'Group:name'>"` with angle brackets that never match `StateFilter`).

**BookingAdapter pattern.** `LocalAdapter` stores everything in Postgres. `GoogleAdapter` stores in both GCal and Postgres. Factory `get_adapter(tenant)` picks the right one based on whether `google_cal_id` and credentials are set. Both adapters have the same interface.

---

## Tech Stack

- **Python 3.11**, aiogram 3.13.1 (long polling), asyncpg, APScheduler
- **Database:** PostgreSQL (schema auto-migrated at startup via `SCHEMA` in `db/models.py`)
- **AI:** Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) with tool use + prompt caching
- **Voice [S1]:** OpenAI Whisper via `openai` SDK
- **Deploy:** Railway, `aria/railway.toml` — main deploy config
- **Mini App [S2]:** React + TypeScript + Vite, hosted on Cloudflare Pages

---

## Deployment

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

### Key env vars
```
ARIA_BOT_TOKEN          — first salon bot token
ANTHROPIC_API_KEY       — Anthropic API key
ARIA_OWNER_TELEGRAM_ID  — platform admin Telegram ID
DATABASE_URL            — postgresql://... (Railway provides this)
MANAGEMENT_BOT_TOKEN    — admin bot token (optional)
OPENAI_API_KEY          — Whisper voice [S1] (optional)
GOOGLE_CALENDAR_CREDENTIALS — service account JSON (optional)
MINIAPP_URL             — Cloudflare Pages URL for Mini App [S2]
```

---

## Rebuild Instructions for Claude Code

To rebuild this project from scratch, read:
- `docs/DOMAIN.md` — Domain definitions & DB schema
- `docs/DECISIONS.md` — Design decisions & bug log
- `docs/STATE.md` — Current project state
- `development.md` — Full technical reference (sections 1–10)

Then reconstruct all files listed in section "6. File-by-File Reference" of `development.md`.
