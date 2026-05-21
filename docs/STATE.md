# Aria — Current Project State

## Last Updated
2026-05-21

## Active Sprint
None — ожидание Sprint 009

## Business Model
- **Соло-мастер**: один owner-бот, мастер = владелец
- **Салон (bundle ~179€)**: owner-бот + N master-ботов для мастеров
- **Платформ-админ**: управляет всеми через admin-бот

## Bot Types
| Bot | Status |
|---|---|
| owner-bot (per-tenant) | ✅ Implemented |
| client-bot (platform-level) | ✅ Sprint 006 |
| master-bot (per-master) | 🔲 Sprint 011 |

## Project Status

| Feature | Status |
|---|---|
| Multi-tenant bot (N bots, one process) | ✅ Implemented |
| AI assistant (Claude Haiku 4.5, tool use) | ✅ Implemented |
| Guided booking wizard (inline keyboard) | ✅ Implemented |
| Schedule views (today/tomorrow/week/upcoming) | ✅ Implemented |
| Google Calendar sync | ✅ Implemented |
| Email monitoring (IMAP → Telegram) | ✅ Implemented |
| VIP clients + reactivation alerts | ✅ Implemented |
| Reminders (day before) + no-show checks (2h after) | ✅ Implemented |
| Service catalogue (categories + items) | ✅ Implemented |
| Voice transcription S1 (OpenAI Whisper) | ✅ Implemented |
| PostgresFSMStorage (FSM survives restarts) | ✅ Implemented |
| Platform admin bot (@AriaReseptionist_Bot) | ✅ Implemented |
| Client self-booking bot (client-bot) | ✅ Sprint 006 |
| Masters DB schema (aria_masters, aria_availability) | ✅ Sprint 007 |
| Masters admin UI (owner-bot Settings) | ✅ Sprint 008 |
| Availability UI in owner-bot | 🔲 Sprint 009 |
| /api/slots respects aria_availability | 🔲 Sprint 010 |
| Master Bot (per-master polling) | 🔲 Sprint 011 |
| Mini App — master selection | 🔲 Sprint 012 |
| Dashboard per master | 🔲 Sprint 013 |
| Auto-reviews | 🔲 Sprint 014 |
| Import DM | 🔲 Sprint 015 |
| Monthly PNG report | 🔲 Sprint 016 |

## Pending Sprints
| Sprint | Goal |
|---|---|
| 009 | Availability UI in owner-bot |
| 010 | /api/slots учитывает aria_availability |
| 011 | Master Bot (отдельный polling) |
| 012 | S3-D Mini App: выбор мастера |
| 013 | S3-E Dashboard по мастерам |
| 014 | S4-A Auto-отзыв |
| 015 | S4-B Import DM |
| 016 | S4-C Monthly PNG отчёт |

## Last Completed Sprint
008-masters-ui — DONE

## Known Open Issues
- No known critical bugs in production as of 2026-05-21
- test_watch_tenants.py: 2 pre-existing failures (aria.main import in test env)
- Mini App integration (S2) pending — no Mini App API endpoints exist yet

## Key Metrics
- Deployment: Railway (single worker process)
- Database: PostgreSQL via asyncpg
- Bot framework: aiogram 3.13.1
- AI model: claude-haiku-4-5-20251001
- Stable snapshot tag: `stable/s1-voice`
- Stable commit (v1.0.0): `230cc350c663c5b7ebd41bb283d16d0a776082ff`

## Branch
Active development branch: `claude/telegram-booking-bot-research-cWjrw`
