Read these files before acting:
- docs/STATE.md
- docs/DOMAIN.md
- planning/sprints/010-source-display/requirements.md
- planning/sprints/010-source-display/blueprint.md
- planning/sprints/010-source-display/acceptance.md

Task: Add booking source display to Telegram bot appointment messages.

Steps:
1. Grep the codebase to find where appointment detail messages are built and
   sent to salon owners.
2. Add a helper function `format_source(source: str) -> str` that maps:
   'bot' → "📱 Бот", 'phone' → "📞 Телефон", 'mini_app' → "🌐 Mini App",
   null/None/unknown → "" (empty string, hide silently).
3. Insert the source line into the appointment detail message template(s),
   shown only when source is non-empty.
4. Stay strictly within scope — do not modify DB schema, dashboard, or
   unrelated handlers.
5. Verify acceptance criteria from acceptance.md before finishing.

When done, provide summary in plain-text copy-friendly format: no markdown,
no headers, minimal tokens.
