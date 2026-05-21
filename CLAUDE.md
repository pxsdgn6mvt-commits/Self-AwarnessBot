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

## Архитектурное решение: два типа ботов (зафиксировано 2026-05-21)

**Owner-bot** (per-tenant, уже работает) — бот для мастера/владельца.
Мастер управляет расписанием, видит записи, настраивает доступность, общается с AI.

**Client-bot** (платформенный, один на всю платформу, S2-D) — бот для клиентов.
Мастер делится ссылкой `t.me/<ClientBot>?start=tenant_{id}` со своими клиентами.
Клиент открывает Mini App → бронирует слот → запись автоматически появляется в
расписании мастера в owner-боте. Мастер получает уведомление.
Telegram Business Mode (бот от имени личного аккаунта) — рассмотрен, отложен.

**Управление доступностью (S3-B)** — мастер через owner-бот открывает/закрывает
конкретные дни, часы, слоты. Mini App показывает только открытые слоты.
Клиент не может забронировать то, что мастер закрыл.

---

## Переменные окружения (Railway Variables)
```
ARIA_BOT_TOKEN          — токен платформенного бота (@BotFather)
CLIENT_BOT_TOKEN        — токен клиентского бота [S2-D] (отдельный от owner-бота)
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

---

## Конкурентный анализ и позиционирование (исследование май 2026)

### Главный вывод
Мастер сказал что букинг-сервисы умеют почти всё что умеет бот — он прав про КЛИЕНТСКУЮ запись.
Но Aria — инструмент для ВЛАДЕЛЬЦА. Проблема: клиентская самозапись отсутствует.
**Решение: добавить Mini App → закрыть пробел и стать уникальным продуктом.**

### Незанятая ниша (никто не совмещает)
1. AI-ассистент для владельца (natural language RU) — есть в Aria
2. Клиентская самозапись через Telegram Mini App — нет нигде
3. White-label multi-tenant SaaS для рынка СНГ — нет нигде
4. **Telegram Business Mode** — бот отвечает от имени личного аккаунта мастера (официальный API, никто не реализовал)

### Ключевые конкуренты
| Продукт | Цена | Что умеет | Чего нет |
|---|---|---|---|
| YClients | ~8000₽/мес | Полный SaaS, склад, зарплаты | AI, Telegram, дорого |
| Dikidi | Бесплатно | Онлайн-запись, CRM | AI, Telegram-native |
| Lyxa AI | $19/мес | AI клиентская запись в TG | Owner dashboard, мультимастер |
| Pleep | $180-430/мес | AI мультиканальный агент | Owner AI, дорого |
| Botseller | 1900₽+20₽/диал | AI запись в мессенджерах | Dashboard, дорого при объёме |
| Starta.one | Pro tier | CRM + NL TG бот (RU) | Только внутри их CRM |
| ZABOT24 | Бесплатно | Простая TG запись | AI, аналитика |
| nazgool97/salon_bot | One-time | Mini App, мультимастер | AI, multi-tenant |

### Рекомендуемое ценообразование
| Тариф | Цена | Что включает |
|---|---|---|
| Старт | 990₽/мес | 1 мастер, AI для владельца, 50 записей/мес |
| Про | 1990₽/мес | 1 мастер, AI + Mini App для клиентов, безлимит |
| Команда | 3490₽/мес | до 5 мастеров, всё из Про + аналитика по мастерам |

### Инфраструктурные затраты
- Railway: $10-25/мес фиксировано
- Anthropic API: ~$1-5/мес на тенанта (при 20 сообщ/день)
- Выход на безубыток: 2-3 платящих тенанта на тарифе Про

---

## Детальный план Mini App (S2) — UI Flow

### Клиентский поток (5 шагов)
1. **Категория услуги** — сетка карточек (Волосы / Ногти / Лицо / Тело)
2. **Услуга** — список с ценой и длительностью
3. **Мастер** — карточки с фото, стажем, рейтингом (или "Любой свободный")
4. **Дата** — календарь (серые = выходные/прошедшие)
5. **Время** — сетка свободных слотов (занятые скрыты)
6. **Подтверждение** — форма с именем + телефоном → запись создана

### Технический стек Mini App
- React + TypeScript + Vite
- [TelegramUI](https://github.com/telegram-mini-apps-dev/TelegramUI) — компоненты
- [TGDates](https://github.com/harshil21/TGDates) — date/time picker
- [Telebook](https://github.com/neSpecc/telebook) — reference implementation
- Авторизация: `Telegram.WebApp.initData` + HMAC-SHA256 валидация на бэкенде
- Хостинг: Cloudflare Pages (бесплатно)

### API endpoints (Flask, добавить в server.py или отдельный файл)
```
GET  /api/services?tenant_id=X       → каталог услуг
GET  /api/masters?service_id=X       → мастера для услуги
GET  /api/slots?master=X&date=Y      → свободные слоты
POST /api/bookings                   → создать запись
GET  /api/my-bookings?user_id=X      → история клиента
```

---

## Новые таблицы DB (S2/S3, ещё не созданы)

```sql
-- Мастера (S3)
CREATE TABLE aria_masters (
    id         SERIAL PRIMARY KEY,
    tenant_id  INT NOT NULL,
    name       TEXT NOT NULL,
    tg_user_id BIGINT,
    photo_url  TEXT,
    bio        TEXT,
    active     BOOLEAN DEFAULT TRUE,
    position   INT DEFAULT 0
);

-- Привязка услуг к мастерам (S3)
CREATE TABLE aria_master_services (
    master_id  INT NOT NULL REFERENCES aria_masters(id),
    service_id INT NOT NULL REFERENCES aria_service_items(id),
    PRIMARY KEY (master_id, service_id)
);

-- Новые колонки в aria_bookings (S2)
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS client_tg_id BIGINT;
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS master_id INT REFERENCES aria_masters(id);
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS client_reminder_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS review_sent BOOLEAN DEFAULT FALSE;

-- Отзывы (S4)
CREATE TABLE aria_reviews (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  INT NOT NULL,
    booking_id BIGINT REFERENCES aria_bookings(id),
    master_id  INT REFERENCES aria_masters(id),
    rating     INT CHECK (rating BETWEEN 1 AND 5),
    text       TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
