# Aria — Project Brain for Claude Code

## Что это за проект
Aria — multi-tenant Telegram bot платформа для beauty-мастеров (салоны, ноготочки, барберы).
Один Railway-процесс запускает N ботов одновременно. Каждый мастер получает свой Telegram-бот.

**Репозиторий:** pxsdgn6mvt-commits/self-awarnessbot  
**Рабочая ветка:** `claude/telegram-booking-bot-research-cWjrw`  
**Деплой:** Railway (worker + web процессы)

---

## Стек
- **Python 3.11**, aiogram 3.x (long polling), asyncpg, APScheduler
- **БД:** PostgreSQL (схема накатывается автоматически при старте через `SCHEMA` в `db/models.py`)
- **AI:** Anthropic Claude Haiku (claude-haiku-4-5-20251001) с tool use + prompt caching
- **Деплой:** Railway, `aria/railway.toml` — главный конфиг деплоя
- **Mini App (планируется):** React + TypeScript + TelegramUI + Vite

---

## Архитектура (критически важно знать)

```
main.py
├── ONE shared Dispatcher (все боты используют один)
├── TenantMiddleware → resolves TenantConfig из bot.token (кэш 30s)
├── Router order: setup → admin → start → menu → quick → email_setup → chat
│   (ВАЖНО: setup первый, chat последний — catch-all)
├── _poll_bot(bot, dp, tenant_id) — long-polling loop per bot
└── _watch_tenants(dp) — каждые 10s стартует/стопает ботов по изменениям в БД
```

### BookingAdapter pattern
- `LocalAdapter` — хранит в PostgreSQL
- `GoogleAdapter` — хранит в GCal + PostgreSQL  
- `get_adapter(tenant)` — выбирает нужный адаптер автоматически
- **Оба адаптера имеют одинаковый интерфейс** — не нарушай это

### FSM критический баг (уже исправлен, не сломай снова)
FSM state хранится как строка `"Group:name"` — НЕ `str(state)` который даёт `"<State 'Group:name'>"` с угловыми скобками. Угловые скобки ломают StateFilter навсегда.

---

## Файловая структура
```
Self-AwarnessBot/
├── CLAUDE.md                    ← этот файл
├── development.md               ← полная техническая документация
├── .env.example                 ← все переменные окружения (без значений)
├── .gitignore                   ← .env защищён, не коммить секреты
│
└── aria/                        ← THE приложение
    ├── main.py                  ← entry point, polling engine
    ├── config.py                ← Settings (env vars)
    ├── tenant.py                ← TenantConfig dataclass
    ├── middleware.py            ← TenantMiddleware
    ├── filters.py               ← SetupRequired / SetupDone
    ├── runtime.py               ← shared bots dict
    │
    ├── db/
    │   ├── models.py            ← SQL SCHEMA (все миграции здесь)
    │   ├── repo.py              ← все DB запросы
    │   └── fsm_storage.py      ← PostgresFSMStorage
    │
    ├── handlers/
    │   ├── setup.py             ← онбординг нового тенанта
    │   ├── admin.py             ← платформенный админ
    │   ├── start.py             ← /start для владельца
    │   ├── menu.py              ← главное меню, дашборд
    │   ├── quick.py             ← мастер записи (wizard)
    │   ├── email_setup.py       ← настройка email-мониторинга
    │   └── chat.py              ← AI чат (catch-all, ВСЕГДА ПОСЛЕДНИЙ)
    │
    └── services/
        ├── ai.py                ← Claude Haiku + tool use
        ├── booking.py           ← LocalAdapter + GoogleAdapter
        ├── scheduler.py         ← APScheduler jobs
        ├── email_monitor.py     ← IMAP → Telegram
        └── commands.py          ← bot command menu registration
```

---

## Переменные окружения (Railway Variables)
```
ARIA_BOT_TOKEN          — токен платформенного бота (@BotFather)
ANTHROPIC_API_KEY       — Anthropic API ключ
ARIA_OWNER_TELEGRAM_ID  — числовой Telegram ID владельца платформы
DATABASE_URL            — postgresql://...
SALON_NAME              — название первого салона (seed)
SALON_OWNER_NAME        — имя владельца
```
Опциональные (Google Calendar):
```
GOOGLE_CALENDAR_CREDENTIALS  — JSON сервисного аккаунта (строкой)
GOOGLE_CALENDAR_ID           — ID календаря
```
**НИКОГДА не коммить реальные значения. Только в Railway Variables или .env (в .gitignore).**

---

## Что уже работает (v1.0.0)
- ✅ Multi-tenant: N ботов из одного процесса
- ✅ AI ассистент (Claude Haiku) — натуральный язык для владельца
- ✅ Мастер записи (inline keyboard wizard)
- ✅ Дашборд: день/неделя/месяц, доходы, загрузка
- ✅ Карточки записей: оплата/перенос/заметка/отмена
- ✅ Каталог услуг с категориями, ценой, длительностью
- ✅ Google Calendar sync (опционально)
- ✅ Email-мониторинг IMAP → Telegram (VIP)
- ✅ VIP клиенты, реактивация 45-дней
- ✅ Напоминания за день до + no-show check через 2ч

## Дорожная карта (что строим)
- 🔲 S1: Голосовые сообщения (voice → Whisper → AI)
- 🔲 S1: Напоминания КЛИЕНТАМ (не только владельцу)
- 🔲 S2: Telegram Mini App — клиентская самозапись
- 🔲 S3: Мульти-мастер внутри тенанта
- 🔲 S4: Auto-отзывы, import DM, monthly report

---

## Правила разработки
1. **Все миграции DB** — только через `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` в `db/models.py`
2. **Новые хендлеры** — регистрировать в `main.py` в `_build_dispatcher()`, соблюдать порядок роутеров
3. **Новые scheduler jobs** — только через `services/scheduler.py`
4. **Тест деплоя** — `python -m aria.main` должен стартовать без ошибок
5. **Ветка** — все изменения в `claude/telegram-booking-bot-research-cWjrw`, пушить после каждого спринта
6. **Не трогать** — `aria/railway.toml` и `aria/Procfile` без необходимости

---

## Как восстановить после поломки
```bash
git log --oneline -10          # найти последний рабочий коммит
git checkout <commit-hash>     # или
git checkout main              # вернуться на стабильную версию (v1.0.0)
```
Стабильный коммит v1.0.0: `230cc350c663c5b7ebd41bb283d16d0a776082ff`
