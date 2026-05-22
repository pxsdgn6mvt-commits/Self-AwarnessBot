# Architecture Decisions

## DECISION-010: GCal sync is non-blocking (create_task, not await)

After a Mini App booking is saved to the database the HTTP response is returned
immediately. The GCal event creation runs in a background asyncio task via
`asyncio.create_task()`. This ensures the client receives a 201 confirmation
in the normal response time regardless of GCal API latency or availability.

## DECISION-011: GCal failure does not block or fail the booking (Mini App)

If the GCal event creation fails for any reason (network error, invalid
credentials, quota exhausted, misconfigured calendar), the booking record is
still persisted in `aria_bookings` and a 201 is returned to the caller.
`gcal_event_id` remains NULL and a WARNING is written to the log.
Resilience over consistency: a saved booking with no GCal event is always
preferable to a lost booking.

## DECISION-012: Mini App API served on Flask $PORT (not a separate port)

The POST /api/booking endpoint runs in the existing Flask web process on $PORT.
This makes the API publicly accessible on Railway without additional port
configuration. The aiohttp sidecar server on port 8081 introduced in Sprint 007
is removed. GCal fire-and-forget uses threading.Thread instead of
asyncio.create_task because Flask runs in a synchronous WSGI context.

## DECISION-013: Telegram WebApp initData as auth for Mini App API

POST /api/booking requires the `X-Telegram-Init-Data` header containing the
initData string produced by the Telegram WebApp SDK. The server verifies it
via HMAC-SHA256 per official TG Bot API docs. Set env var
`TELEGRAM_WEBAPP_SKIP_AUTH=true` to bypass verification in local dev/testing.

