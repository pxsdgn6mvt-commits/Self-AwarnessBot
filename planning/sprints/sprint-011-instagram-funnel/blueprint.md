# Sprint 011 — Instagram Funnel: Blueprint

## Architecture

This sprint produces only content/copy assets. No code changes.

### Directory Layout

```
planning/sprints/sprint-011-instagram-funnel/
├── requirements.md       — what and why
├── blueprint.md          — this file; how it fits together
├── acceptance.md         — done criteria
├── handoff-prompt.md     — prompt to recreate this sprint in a new session
└── dm-templates/
    ├── ru-owner.md       — RU salon owner DM sequence
    ├── ru-master.md      — RU stylist/master DM sequence
    ├── fi-owner.md       — FI salon owner DM sequence
    ├── fi-master.md      — FI stylist/beauty pro DM sequence
    ├── en-owner.md       — EN salon owner DM sequence
    └── en-master.md      — EN stylist/beauty pro DM sequence
```

## Message Flow per Template

```
Comment on post
    └─▶ Message 1: intro + guide offer + follow-check
            ├─▶ [Following]     → Message 2a: guide link + Aria CTA
            └─▶ [Not following] → Message 2b: follow prompt
                                      └─▶ (user follows & returns)
                                              └─▶ Message 2a

Message 2a delivered
    └─▶ +24h → Message 3: soft follow-up + Aria CTA
```

## Template File Format

Each file uses the following structure:

- H1: `DM Templates — {LANG} — {Segment}`
- H2 per message: `Message N (context)`
- Separator: `-----`
- Inline button labels in `[brackets]`

## Localisation Notes

- **RU**: Informal `ты` register throughout. Emoji used lightly for warmth.
- **FI**: Conversational `sinä` register (informal). Emoji mirrors RU usage.
- **EN**: Casual, direct tone. Mirrors emoji density of other locales.

## CTAs

All final CTAs resolve to Aria free trial page. The placeholder `[🚀 ...]` button text is copywriter-final and should not be changed without approval.
