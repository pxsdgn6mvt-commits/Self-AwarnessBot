# Sprint 012 — Waitlist Feature Requirements

## Goal
Replace direct Stripe purchase CTAs with a waitlist flow so AIBeautyKit can
collect leads before reopening paid subscriptions.

## In scope
- Waitlist signup form page (waitlist.html)
- Thank-you confirmation page (waitlist-thanks.html)
- Backend endpoint: POST /api/waitlist — validates, saves to DB, emails admin
- DB table: waitlist_entries
- Guide pages for all 6 audience segments (en/ru/fi × owner/master)
- All guide CTAs point to /waitlist instead of Stripe

## Out of scope
- Bot code changes
- Existing landing page (index.html) CTA changes
- Admin dashboard for viewing entries
- Email to the user who signed up (only admin notification)

## Functional requirements
1. Form collects: name (text), email (email), country (select: Finland / Russia / Other)
2. All three fields are required — 400 on missing fields
3. Successful submission inserts row into waitlist_entries and redirects to /waitlist/thanks
4. Admin notification email sent via SMTP env vars (gracefully skipped if unconfigured)
5. Guide pages exist for: en-owner, en-master, ru-owner, ru-master, fi-owner, fi-master
6. Each guide CTA links to /waitlist (primary) and https://t.me/AIBeautyKitinc (secondary)

## Non-functional requirements
- Dark theme (#0a0a0f bg, #c9a96e gold) consistent across waitlist and guide pages
- Pages load without JS
- No external CSS/JS dependencies beyond Google Fonts (guides only use system fonts)
