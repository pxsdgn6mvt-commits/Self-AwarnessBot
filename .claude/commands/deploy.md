Prepare and push code for Railway deployment.

Steps:
1. Run: git status (check nothing unintended is staged)
2. Run: python -c "import aria.main" (syntax check)
3. Check aria/railway.toml and aria/Procfile are intact
4. Commit any unstaged changes with a clear message
5. Push to branch: claude/telegram-booking-bot-research-cWjrw
6. Report what was pushed and remind to trigger Railway redeploy

Never push to main without explicit user confirmation.
Never use --force push.
