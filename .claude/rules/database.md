# Database Rules for Aria

- ALL schema changes go in `aria/db/models.py` SCHEMA string
- Migrations: ONLY `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — never DROP, never change type
- New tables: `CREATE TABLE IF NOT EXISTS`
- New indexes: `CREATE INDEX IF NOT EXISTS`
- All queries in `aria/db/repo.py` — no raw SQL in handlers or services
- Multi-tenant: EVERY query must filter by `tenant_id`
- Use asyncpg connection from pool — never create new connections manually
