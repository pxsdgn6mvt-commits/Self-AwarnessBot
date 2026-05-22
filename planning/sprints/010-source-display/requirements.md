# Sprint 010 — Source Display in Bot

## Business Goal
Show the booking source (bot / phone / mini_app) to salon owners when they
view appointment info inside the Telegram bot.

## Users
- Salon owner (receives booking notifications and views appointment details)

## Scope
- Read existing `source` field from bookings table (already populated)
- Display source label in bot messages that show appointment info

## Out of Scope
- Dashboard changes
- Adding new source values
- Filtering or stats by source

## Inputs
- Existing `source` column in `bookings` table (values: 'bot', 'phone', 'mini_app')

## Outputs
- Bot messages showing appointment details include a human-readable source label
