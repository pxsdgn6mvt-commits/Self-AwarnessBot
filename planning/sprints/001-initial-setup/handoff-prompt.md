# Sprint 001 — Architect/Builder Bootstrap
# Handoff Prompt for Claude Code (Builder)

## Your Role
You are the Builder Layer. Execute this blueprint exactly.
Do not invent, refactor, or expand scope.
The source of truth is this prompt and the existing `development.md`.

---

## Context
You are bootstrapping the Architect/Builder methodology structure
inside an existing Python/aiogram Telegram bot project called "Aria"
(Multi-Tenant Salon Bot Platform).

The project already has: `aria/`, `miniapp/`, `server.py`,
`requirements.txt`, `Procfile`, `railway.toml`, `.env.example`.

The master knowledge document is `development.md` in the repo root.
You must READ it fully before doing anything else.

---

## Step 1 — Read First (mandatory)
Read the following files before writing a single line:
1. `development.md` — full file, do not skip sections

---

## Step 2 — Create Directory Structure

```
mkdir -p .claude
mkdir -p docs
mkdir -p planning/sprints/001-initial-setup
```

---

## Step 3 — Create Files

### 3.1 `.claude/CLAUDE.md`
Extract from `development.md` and write a file with these sections:
- Aria — Project Overview for Architect
- What This Project Does (section 1 verbatim)
- Architecture Overview (section 2 verbatim)
- Tech Stack (verbatim)
- Deployment (section 8 verbatim)
- Rebuild Instructions for Claude Code

### 3.2 `docs/DOMAIN.md`
Extract and write:
- Aria — Domain Definitions
- Core Entities (Database Schema section verbatim)
- User Roles
- Feature Glossary (section 9 verbatim)

### 3.3 `docs/DECISIONS.md`
Extract and write:
- Aria — Architectural Decisions Log
- Key Design Decisions (from section 2)
- Critical Bugs Found and Fixed (section 7 verbatim)
- Lessons Learned

### 3.4 `docs/STATE.md`
Create fresh (do not copy from development.md):
- Last Updated: today's date
- Active Sprint: 001-initial-setup
- Project Status: feature checklist
- Last Completed Sprint: None
- Known Open Issues
- Key Metrics

### 3.5 `planning/sprints/001-initial-setup/requirements.md`
- Goal, Business Objectives, Scope, Out of Scope

### 3.6 `planning/sprints/001-initial-setup/blueprint.md`
- Files to Create table
- Files to Modify table
- Files NOT to Touch
- Technical Approach

### 3.7 `planning/sprints/001-initial-setup/acceptance.md`
- Checklist of all acceptance criteria

### 3.8 `planning/sprints/001-initial-setup/handoff-prompt.md`
Write the contents of this very prompt into that file (self-referential).

---

## Step 4 — Patch `development.md`
Prepend the following block to the TOP of `development.md`:

```
<!--
=============================================================
ARCHITECT/BUILDER NOTE — Sprint 001 completed
This file remains the full technical reference.
For structured docs, see:
  - .claude/CLAUDE.md      ← Architect context
  - docs/DOMAIN.md         ← Domain definitions & DB schema
  - docs/DECISIONS.md      ← Design decisions & bug log
  - docs/STATE.md          ← Current project state
  - planning/sprints/      ← Sprint history
=============================================================
-->
```

---

## Step 5 — Completion Summary
Output a summary with:
- Files Created (list)
- Files Modified (list)
- Files NOT Touched (confirmed)
- Assumptions Made
- Acceptance Criteria Status (checklist with ✅/❌)
- Ready for Next Sprint: YES/NO

---

## Constraints
- Do NOT modify any `.py` files
- Do NOT modify `requirements.txt`, `Procfile`, `railway.toml`
- Do NOT create any new Python modules
- Do NOT run the bot or any Python scripts
- Stay strictly within this blueprint. No scope creep.
