# Python Rules for Aria

- Python 3.11, async/await everywhere (no blocking calls in handlers)
- asyncpg for all DB — always parameterized queries ($1, $2...), never f-string SQL
- Type hints on all new functions
- No comments unless the WHY is non-obvious
- No docstrings on internal functions
- Imports: stdlib → third-party → local (separated by blank lines)
- Error handling only at system boundaries (Telegram updates, external APIs)
- Trust internal code — no defensive checks for impossible states
