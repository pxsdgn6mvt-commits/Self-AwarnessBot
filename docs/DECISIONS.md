# Aria Bot — Architecture Decisions

## DECISION-014 — auth_date validation in verify_telegram_webapp

**Date:** 2026-05-22  
**Sprint:** 009  
**Status:** Accepted

auth_date is validated against time.time() inside verify_telegram_webapp().
Max age is configurable via TELEGRAM_AUTH_MAX_AGE_SECONDS (default 600s = 10 min).
Prevents replay attacks on POST /api/booking.
TELEGRAM_WEBAPP_SKIP_AUTH=true bypasses all checks (dev mode).
