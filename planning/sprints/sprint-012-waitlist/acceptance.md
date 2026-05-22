# Sprint 012 — Acceptance Criteria

## Routes
- [ ] GET /waitlist returns 200 with waitlist.html content
- [ ] GET /waitlist/thanks returns 200 with waitlist-thanks.html content
- [ ] POST /api/waitlist with valid fields returns 302 redirect to /waitlist/thanks
- [ ] POST /api/waitlist with missing field(s) returns 400
- [ ] GET /guides/en-owner.html returns 200
- [ ] GET /guides/en-master.html returns 200
- [ ] GET /guides/ru-owner.html returns 200
- [ ] GET /guides/ru-master.html returns 200
- [ ] GET /guides/fi-owner.html returns 200
- [ ] GET /guides/fi-master.html returns 200

## Database
- [ ] waitlist_entries table created on startup (idempotent via IF NOT EXISTS)
- [ ] Successful POST inserts a row with correct name, email, country, created_at

## Waitlist form page
- [ ] Dark background (#0a0a0f)
- [ ] Gold accent (#c9a96e) visible on submit button and branding
- [ ] Form has name (text), email (email), country (select) fields
- [ ] Country select includes: Finland, Russia, Other
- [ ] Form POSTs to /api/waitlist
- [ ] Telegram link https://t.me/AIBeautyKitinc present below form
- [ ] Page renders without JavaScript

## Waitlist thanks page
- [ ] Shows confirmation message "You're on the list."
- [ ] Telegram link https://t.me/AIBeautyKitinc with text "Join our Telegram while you wait →"
- [ ] No form present
- [ ] Same dark gold theme

## Guide pages (all 6)
- [ ] Primary CTA href="/waitlist"
- [ ] EN guides: button text "Join the Waitlist →"
- [ ] RU guides: button text "Войти в список →"
- [ ] FI guides: button text "Liity jonoon →"
- [ ] Secondary CTA href="https://t.me/AIBeautyKitinc"
- [ ] EN guides: secondary text "Join Telegram →"
- [ ] RU guides: secondary text "Telegram канал →"
- [ ] FI guides: secondary text "Telegram-kanava →"
- [ ] No href="https://buy.stripe.com/..." anywhere in guides/

## Email
- [ ] Admin email sent when SMTP env vars are set
- [ ] Server logs warning (not error) and continues when SMTP vars are absent
- [ ] Subject is "New waitlist signup — AIBeautyKit"

## Bot code
- [ ] No bot files modified (aria/ directory untouched)
