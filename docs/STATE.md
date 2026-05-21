# Aria — Current Project State

## Last Updated
2026-05-21

## Active Sprint
None — ожидание Sprint 007

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
| Mini App (S2) — client self-booking | 🔲 Not started |
| Multi-master per tenant (S3) | 🔲 Not started |
| Auto-reviews, monthly report (S4) | 🔲 Not started |
| Client reminders (not just owner) | 🔲 Not started |

## Last Completed Sprint
006-client-bot — DONE

## Known Open Issues
- No known critical bugs in production as of 2026-05-21
- All bugs from v1.0 refactor (Bugs 1–4) and S1 voice (Bugs 5–7) are fixed
- Mini App integration (S2) pending — no Mini App API endpoints exist yet

## Key Metrics
- Deployment: Railway (single worker process)
- Database: PostgreSQL via asyncpg
- Bot framework: aiogram 3.13.1
- AI model: claude-haiku-4-5-20251001
- Stable snapshot tag: `stable/s1-voice`
- Stable commit (v1.0.0): `230cc350c663c5b7ebd41bb283d16d0a776082ff`

## Branch
Active development branch: `claude/telegram-booking-bot-research-ZygWD`
