# Project State

Updated: 2026-05-21

## Completed sprints

| Sprint | Description | Status |
|--------|-------------|--------|
| 001 | Multi-tenant polling core | ✅ done |
| 002 | VIP system, scheduler, email monitor | ✅ done |
| 003 | Mini App skeleton + API layer (aiohttp) | ✅ done |

## Current architecture

```
Railway:
  web    → gunicorn server:app          (Flask, landing page, /api/chat)
  worker → python -m aria.main         (asyncio, polling, aiohttp API on PORT_API)
```

## Active technical debt

| ID | Description | Sprint |
|----|-------------|--------|
| TD-001 | is_active filter missing from service catalogue queries | 004 |
| TD-002 | Slot conflict checking not implemented (slots are fixed 09-18) | 005 |

## Open variables (Railway)

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| ARIA_BOT_TOKEN | ✅ | — | Main bot token |
| DATABASE_URL | ✅ | — | asyncpg DSN |
| ANTHROPIC_API_KEY | ✅ | — | AI responses |
| PORT_API | ⚠️ | 8081 | aiohttp Mini App API port |
