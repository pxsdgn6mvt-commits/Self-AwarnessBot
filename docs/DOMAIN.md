# Aria — Domain Definitions

## Core Entities

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

## User Roles

- **Platform Admin**: manages all salon bots, sends broadcasts, grants VIP, resets/deactivates bots
- **Salon Owner**: uses AI assistant, appointment booking wizard, calendar sync, email monitoring
- **End Client**: interacts with salon bot to book appointments (S2 Mini App — not yet implemented)

---

## Feature Glossary

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

### Voice Transcription [S1]
1. Owner sends voice message
2. `chat.py` detects `message.voice` → calls `voice.transcribe(bot, file_id, lang)`
3. Whisper returns transcript text
4. Transcript goes through same AI/bypass pipeline as typed text
5. Bot responds with echo + AI reply in one message

### Guided Booking Wizard
- All inline keyboard driven, no typing required
- Wizard message is edited in-place at each step (not re-sent)
- `wizard_msg_id` stored in FSM data to find the message
- Custom date accepts: `DD.MM`, `DD.MM.YYYY`, `YYYY-MM-DD`, `DD/MM`
- Custom time accepts: `HH:MM`
