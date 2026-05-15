# Aria — Multi-Tenant Salon Bot Platform

AI-receptionist for beauty salons. One Railway deployment, unlimited salon bots, each with its own Telegram bot token and Google Calendar.

---

## Google Calendar Setup — Full Guide

### Architecture

One shared Google service account for the entire platform. Each salon owner shares their personal Google Calendar with this account — the bot reads and writes directly to it. As the platform operator you never touch client calendars — each client does the 3-minute setup themselves.

---

### Step 1 — Platform Setup (done once by you)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project
3. **APIs & Services → Library** → search **Google Calendar API** → Enable
4. **APIs & Services → Credentials → Create Credentials → Service Account**
5. Open the created account → **Keys → Add Key → JSON** → download the file
6. Paste the entire JSON file contents into the Railway variable `GOOGLE_CALENDAR_CREDENTIALS`
7. Note the service account email (looks like `xxx@yyy.iam.gserviceaccount.com`) — the bot shows it automatically during client setup

---

### Step 2 — Client Setup (done by each salon owner)

The client opens their bot → `/start` → completes the setup wizard:
- Salon name, owner name, services, working hours, timezone
- On the last step the bot displays the service account email and instructions

The client goes to **calendar.google.com** → ⚙️ Settings → selects their calendar → section **"Share with specific people"** → **"+ Add people"** → pastes the service account email → permission **"Make changes to events"** → Save.

On the same settings page, scroll down to **"Integrate calendar"** → copy the **Calendar ID**.

Return to the bot, paste the Calendar ID (or the full iCal link — the bot extracts the ID automatically).

---

### What `/set_cal` Accepts

The bot automatically extracts the ID from any format:

| What the client sends | What the bot saves |
|---|---|
| `name@gmail.com` | `name@gmail.com` |
| `abc123@group.calendar.google.com` | `abc123@group.calendar.google.com` |
| Full iCal URL `https://calendar.google.com/calendar/ical/abc123%40group.../basic.ics` | `abc123@group.calendar.google.com` |

---

### Bot Commands

**Owner commands** (visible in the bot menu for the salon owner):

| Command | What it does |
|---|---|
| `/status` | Shows calendar ID, service account email, timezone |
| `/test_cal` | Live GCal API call — shows exact error if any |
| `/set_cal` | Update Calendar ID (accepts URL or bare ID) |
| `/set_tz` | Update timezone |
| `/help` | List of example phrases |
| `/reset` | Clear conversation history |

**Admin commands** (main bot only, admin Telegram ID required):

| Command | What it does |
|---|---|
| `/list_bots` | All tenants with ID, setup status, owner_tg_id, calendar ID |
| `/add_bot` | Add a new salon bot token |
| `/reset_bot <id>` | Reset setup → client goes through wizard again |
| `/del_bot <id>` | Deactivate a bot |

---

### Errors and Fixes

**404 — calendar not found**
→ Service account has not been added to the calendar sharing settings.
→ Client must add the service account email with "Make changes to events" permission.

**403 — API disabled**
→ Google Calendar API is not enabled in Cloud Console.
→ Fix: APIs & Services → Google Calendar API → Enable.

**Adapter shows LocalAdapter instead of GoogleAdapter**
→ Either `google_cal_id` is not set (use `/set_cal`), or `GOOGLE_CALENDAR_CREDENTIALS` is missing in Railway Variables.

**Bot says "local storage only"**
→ Fixed. Was a bug where the system prompt only checked per-tenant credentials, not the platform-level ones.

**Client sent an iCal link instead of Calendar ID**
→ Fixed. Bot now auto-extracts the ID from any Google Calendar URL format.

---

### New Client Checklist

- [ ] Client completed `/start` wizard
- [ ] Service account email added to client's Google Calendar with "Make changes to events" permission
- [ ] Correct Calendar ID set via `/set_cal`
- [ ] `/test_cal` returns `✅ GCal API works`
- [ ] Test booking created and visible in client's Google Calendar

---

### Railway Environment Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Main Telegram bot token |
| `DATABASE_URL` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `GOOGLE_CALENDAR_CREDENTIALS` | Full JSON content of service account key file |
| `GOOGLE_CALENDAR_ID` | Calendar ID for the main (first) bot |
| `ADMIN_TELEGRAM_ID` | Telegram user ID of the platform admin |
| `OWNER_TELEGRAM_ID` | Telegram user ID of the main bot owner |
| `SALON_NAME` | Name of the main salon |
| `OWNER_NAME` | Name of the main salon owner |
| `SALON_SERVICES` | Comma-separated list of services |
| `SALON_HOURS` | Working hours description |
| `SALON_OPEN_HOUR` | Opening hour (integer, local time) |
| `SALON_CLOSE_HOUR` | Closing hour (integer, local time) |
| `SALON_SLOT_MINUTES` | Appointment slot duration in minutes |
| `SALON_WORKING_DAYS` | Working days as ISO weekday numbers (e.g. `1,2,3,4,5,6`) |
