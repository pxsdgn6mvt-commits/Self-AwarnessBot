# Blueprint — Sprint 010

## Source Label Mapping
Map raw DB values to readable Russian/English labels:
- 'bot'      → "📱 Бот"
- 'phone'    → "📞 Телефон"
- 'mini_app' → "🌐 Mini App"
- None/null  → "" (hide field silently)

## Files to Modify
1. Locate the message formatting function(s) that build appointment detail text
   (likely in aria/handlers/ or aria/utils/formatters.py or similar).
2. Add a `format_source(source: str) -> str` helper.
3. Inject source line into appointment detail message template.

## Implementation Steps
1. Read STATE.md and DOMAIN.md to confirm bookings table schema and message
   formatting patterns used in the codebase.
2. Grep for where appointment/booking details are formatted into bot messages.
3. Add helper function `format_source`.
4. Update message template(s) to include source line when source is not null.
5. No DB migrations needed.
