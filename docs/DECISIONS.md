# Architecture Decisions

## DECISION-010: GCal sync is non-blocking (create_task, not await)

After a Mini App booking is saved to the database the HTTP response is returned
immediately. The GCal event creation runs in a background asyncio task via
`asyncio.create_task()`. This ensures the client receives a 201 confirmation
in the normal response time regardless of GCal API latency or availability.

## DECISION-011: GCal failure does not block or fail the booking

If the GCal event creation fails for any reason (network error, invalid
credentials, quota exhausted, misconfigured calendar), the booking record is
still persisted in `aria_bookings` and a 201 is returned to the caller.
`gcal_event_id` remains NULL and a WARNING is written to the log.
Resilience over consistency: a saved booking with no GCal event is always
preferable to a lost booking.
