# Sprint 012 — Waitlist Blueprint

## DB schema addition (server.py startup)
```sql
CREATE TABLE IF NOT EXISTS waitlist_entries (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    country TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
Connection via DATABASE_URL env var using psycopg2.

## Routes added to server.py
| Method | Path              | Handler          |
|--------|-------------------|------------------|
| GET    | /waitlist         | serve waitlist.html |
| GET    | /waitlist/thanks  | serve waitlist-thanks.html |
| POST   | /api/waitlist     | validate → insert → email → redirect |
| GET    | /guides/<filename>| serve guides/<filename> |

## POST /api/waitlist logic
1. Read form fields: name, email, country
2. If any missing → return 400
3. INSERT INTO waitlist_entries (name, email, country)
4. Call _send_admin_email() — logs warning and continues on SMTP misconfiguration
5. redirect("/waitlist/thanks")

## Email (admin notification)
- Subject: "New waitlist signup — AIBeautyKit"
- Body: name, email, country, UTC timestamp
- Env vars: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, ADMIN_EMAIL
- Uses smtplib + STARTTLS

## File manifest
```
server.py              (modified)
waitlist.html          (new)
waitlist-thanks.html   (new)
guides/en-owner.html   (new)
guides/en-master.html  (new)
guides/ru-owner.html   (new)
guides/ru-master.html  (new)
guides/fi-owner.html   (new)
guides/fi-master.html  (new)
```

## Style tokens (consistent across all new pages)
- bg: #0a0a0f
- bg2: #111118
- bg3: #1a1a24
- gold: #c9a96e
- text: #f0ece4
- muted: #8a8496
