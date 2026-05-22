# AIBeautyKit Web — State

## Active sprint
Sprint 012 — Waitlist feature
Branch: claude/aibeautykit-waitlist-Np8Kd

## Completed sprints
- Sprint 012: Waitlist flow (waitlist.html, waitlist-thanks.html, 6 guide pages, DB table, /api/waitlist)

## Web stack
- Flask + Gunicorn (server.py)
- PostgreSQL via DATABASE_URL / psycopg2
- Static HTML served via _read_html()
- Anthropic API for /api/chat sales assistant

## Key env vars (web)
| Var            | Purpose |
|----------------|---------|
| DATABASE_URL   | PostgreSQL connection |
| ANTHROPIC_API_KEY | Claude Haiku for sales chat |
| ADMIN_EMAIL    | Waitlist notification recipient |
| SMTP_HOST      | SMTP server hostname |
| SMTP_PORT      | SMTP port (default 587) |
| SMTP_USER      | SMTP login |
| SMTP_PASSWORD  | SMTP password |

## Routes
| Method | Path              | Notes |
|--------|-------------------|-------|
| GET    | /                 | index.html |
| GET    | /thank-you        | thank-you.html |
| GET    | /how-it-works     | how-it-works.html |
| GET    | /faq              | faq.html |
| GET    | /waitlist         | waitlist.html |
| GET    | /waitlist/thanks  | waitlist-thanks.html |
| GET    | /guides/<file>    | guides/<file> |
| GET    | /healthz          | "ok" 200 |
| POST   | /api/waitlist     | insert waitlist entry, email admin |
| POST   | /api/chat         | Claude Haiku sales assistant |
