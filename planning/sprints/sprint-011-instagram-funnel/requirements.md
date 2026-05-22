# Sprint 011 — Instagram Funnel: Requirements

## Goal

Build and document an Instagram DM funnel that converts post commenters into Aria trial sign-ups. The funnel uses a free lead-magnet guide (PDF) as an entry hook, gated behind an account follow-check.

## Target Audiences

| Segment | Description |
|---|---|
| Salon Owner (RU) | Russian-speaking salon business owners |
| Stylist / Master (RU) | Russian-speaking independent beauty professionals |
| Salon Owner (FI) | Finnish-speaking salon business owners |
| Stylist / Beauty Pro (FI) | Finnish-speaking independent beauty professionals |
| Salon Owner (EN) | English-speaking salon business owners |
| Stylist / Beauty Pro (EN) | English-speaking beauty professionals |

## Funnel Flow

1. User comments on a post
2. Bot sends Message 1 — asks if they follow the account
3a. User confirms follow → Bot sends Message 2a (guide + CTA to try Aria)
3b. User is not following → Bot sends Message 2b (follow prompt, no guide)
4. 24 hours after guide delivery → Bot sends Message 3 (follow-up + Aria CTA)

## Lead Magnet Content (per segment)

- **Owners**: "5 reasons your salon is losing money without automation"
- **Masters / Stylists**: "How to manage bookings without chaos and keep clients coming back"

## CTA Destination

All CTAs link to Aria 14-day free trial. No credit card required.

## Deliverables

- 6 DM template files (2 languages × 3 locales): `dm-templates/`
- Sprint blueprint, acceptance criteria, and handoff prompt

## Out of Scope

- Bot code changes
- PDF guide creation
- Instagram API integration
