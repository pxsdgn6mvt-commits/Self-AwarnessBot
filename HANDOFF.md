# Aria — Handoff для нового чата Claude Code

## Как пользоваться этим файлом
Прочитай этот файл целиком. Найди первый пункт со статусом 🔲 в разделе "Дорожная карта".
Это и есть следующая задача. Реализуй её, обнови статус на ✅, закоммить и запушь.

---

## Окружение
```
Репозиторий:  pxsdgn6mvt-commits/Self-AwarnessBot
Рабочая папка: /home/user/Self-AwarnessBot
Рабочая ветка: claude/telegram-booking-bot-research-cWjrw
Стабильная:   main (коммит 230cc350c663c5b7ebd41bb283d16d0a776082ff = v1.0.0)
Деплой:       Railway (автодеплой при пуше в main)
```

## Переменные окружения (в Railway Variables, не в коде)
```
ARIA_BOT_TOKEN          — токен бота от @BotFather
ANTHROPIC_API_KEY       — Anthropic API ключ
ARIA_OWNER_TELEGRAM_ID  — числовой Telegram ID владельца платформы
DATABASE_URL            — postgresql://...
SALON_NAME              — название салона (seed для первого тенанта)
SALON_OWNER_NAME        — имя владельца
GOOGLE_CALENDAR_CREDENTIALS  — (опционально) JSON сервисного аккаунта
GOOGLE_CALENDAR_ID           — (опционально) ID Google календаря
MINIAPP_URL                  — URL задеплоенного Mini App (Cloudflare Pages / Railway)
MINIAPP_ORIGIN               — CORS origin Mini App (совпадает с MINIAPP_URL без пути)
```

---

## Архитектура (обязательно знать перед правками)

**Стек:** Python 3.11, aiogram 3.x (long polling), asyncpg, APScheduler, Claude Haiku API

```
main.py
├── ONE shared Dispatcher для всех ботов
├── TenantMiddleware → резолвит TenantConfig из bot.token (кэш 30s)
├── Порядок роутеров: setup → admin → start → menu → quick → email_setup → chat
│   КРИТИЧНО: setup первый, chat ПОСЛЕДНИЙ (catch-all)
└── _watch_tenants() — каждые 10s стартует/стопает ботов по изменениям в БД
```

**BookingAdapter:** LocalAdapter (Postgres) или GoogleAdapter (GCal+Postgres).
`get_adapter(tenant)` выбирает автоматически. Интерфейс одинаковый — не нарушай.

**FSM:** state хранится как строка `"Group:name"` — НЕ `str(state)`.
`str(state)` даёт `"<State 'Group:name'>"` с угловыми скобками → StateFilter никогда не сработает.

**DB миграции:** только `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` в `aria/db/models.py`.
Никогда не DROP, не меняй тип существующей колонки.

**Новые хендлеры:** регистрировать в `main.py` → `_build_dispatcher()`, ДО `chat.router`.

---

## Что уже работает (v1.0.0 на main)
- ✅ Multi-tenant: N ботов из одного процесса
- ✅ AI ассистент (Claude Haiku) — натуральный язык для владельца (RU)
- ✅ Мастер записи: категория → услуга → дата → время → имя (inline keyboard wizard)
- ✅ Дашборд: день/неделя/месяц, выручка, загрузка, доля мастера, налог
- ✅ Карточки записей: 💰 Оплата · ✏️ Перенос · 📝 Заметка · ❌ Отмена
- ✅ Каталог услуг с категориями, ценой, длительностью (inline редактирование)
- ✅ Google Calendar sync (опционально)
- ✅ Email-мониторинг IMAP → Telegram (только VIP тенанты)
- ✅ VIP клиенты + реактивация через 45 дней
- ✅ Напоминания владельцу за день до записи + no-show check через 2ч
- ✅ Платформенный admin: добавление ботов, VIP статус, broadcast

---

## Дорожная карта

### S1 — Quick Wins (~1 нед, только Python)

- ✅ **S1-A: Голосовые сообщения** (voice → текст → AI)
  - `aria/services/voice.py` — Whisper транскрипция
  - `aria/handlers/chat.py` — voice branch перед текстом
  - `aria/config.py` + `requirements.txt` — OPENAI_API_KEY, openai>=1.30.0
  - Env var: `OPENAI_API_KEY` в Railway Variables

- ✅ **S1-B: Напоминания клиентам**
  - `aria/db/models.py` — колонки `client_tg_id` и `client_reminder_sent` в aria_bookings
  - `aria/db/repo.py` — `create_booking` принимает `client_tg_id`; добавлен `mark_client_reminder_sent`
  - `aria/services/scheduler.py` — после reminder владельцу шлёт клиенту если `client_tg_id IS NOT NULL`
  - `client_tg_id` заполняется через Mini App (S2); из wizard остаётся NULL

---

### S2 — Telegram Mini App (2-4 нед, Python + React)

**Цель:** клиенты записываются сами через Telegram, не беспокоя владельца.

**Архитектурное решение (зафиксировано 2026-05-21):**
Клиентский бот — **отдельный платформенный бот** (не per-tenant, не тот же что у мастера).
Один бот на всю платформу, маршрутизация по tenant через deep link.
Мастер делится ссылкой `t.me/<ClientBot>?start=tenant_{id}` со своими клиентами.
Клиент → открывает Mini App → бронирует → запись появляется в расписании мастера автоматически.
Мастер видит новые записи от клиентов в своём owner-боте (уведомление + в расписании).
Telegram Business Mode — рассматривался, отклонён как излишне сложный для данного этапа.

- ✅ **S2-A: Backend API endpoints** (добавить в `server.py`)
  ```
  GET  /api/services?tenant_id=X        → каталог услуг из aria_service_categories + items
  GET  /api/slots?tenant_id=X&date=Y    → свободные слоты на дату (из booking.py логика)
  POST /api/bookings                    → создать запись (валидация initData!)
  GET  /api/my-bookings?user_id=X&tenant_id=Y → история клиента
  ```
  - Валидация `Telegram.WebApp.initData` через HMAC-SHA256 с bot token ОБЯЗАТЕЛЬНА
  - CORS: разрешить только с домена Mini App (Cloudflare Pages)

- ✅ **S2-B: React Mini App** (новая папка `miniapp/`)
  - Стек: React + TypeScript + Vite
  - UI: [TelegramUI](https://github.com/telegram-mini-apps-dev/TelegramUI)
  - Дата: [TGDates](https://github.com/harshil21/TGDates) или react-day-picker
  - Reference: [Telebook](https://github.com/neSpecc/telebook)
  - 6 экранов: Категория → Услуга → Дата → Время → Форма → Подтверждение
  - Авторизация: `window.Telegram.WebApp.initData` передаётся в каждый API запрос
  - Хостинг: Cloudflare Pages (бесплатно) или Railway static

- ✅ **S2-C: Интеграция owner-бота с Mini App**
  - Кнопка "Записаться" в боте открывает Mini App с `tenant_id` в URL
  - Когда клиент завершил запись → бот отправляет уведомление владельцу
  - Сохранить `client_tg_id` в `aria_bookings` при записи через Mini App

- 🔲 **S2-D: Клиентский бот (платформенный)**
  - Env var: `CLIENT_BOT_TOKEN` — отдельный токен только для клиентских взаимодействий
  - `/start tenant_{id}` deep link → бот отвечает кнопкой "Записаться" (WebApp)
  - Мастер делится ссылкой: `t.me/<bot>?start=tenant_{id}`
  - При завершении записи через Mini App → уведомление уходит в owner-бот тенанта
  - `client_tg_id` берётся из `initData.user.id` и сохраняется в `aria_bookings`
  - Клиент может написать боту → AI отвечает (как в owner-боте, но в режиме клиента)
  - Реализация: отдельный `aria/handlers/client_bot.py` + polling в `main.py`

---

### S3 — Мульти-мастер + Управление доступностью

**Цель:** салоны с 2+ мастерами; каждый мастер полностью контролирует своё расписание.

**Архитектурное решение (зафиксировано 2026-05-21):**
Мастера управляют доступностью через owner-бот (открыть/закрыть дни и слоты).
Клиентский Mini App показывает только те слоты, которые мастер открыл.
При записи клиента — слот автоматически исчезает из доступных у других клиентов.

- 🔲 **S3-A: DB схема мастеров**
  ```sql
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
  CREATE TABLE aria_master_services (
      master_id  INT NOT NULL REFERENCES aria_masters(id),
      service_id INT NOT NULL REFERENCES aria_service_items(id),
      PRIMARY KEY (master_id, service_id)
  );
  ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS master_id INT REFERENCES aria_masters(id);
  ```

- 🔲 **S3-B: Управление доступностью мастера**
  Мастер полностью контролирует когда он принимает клиентов.
  ```sql
  CREATE TABLE aria_availability (
      id          SERIAL PRIMARY KEY,
      tenant_id   INT NOT NULL,
      master_id   INT REFERENCES aria_masters(id),  -- NULL = весь тенант
      date        DATE,                              -- NULL = еженедельное правило
      weekday     INT,                               -- 1=Пн…7=Вс, NULL если date задан
      time_from   TIME,                              -- NULL = весь день закрыт
      time_to     TIME,
      is_open     BOOLEAN NOT NULL DEFAULT TRUE,     -- FALSE = заблокировано
      note        TEXT
  );
  ```
  - Owner-бот UI: кнопки "Открыть день / Закрыть день / Настроить часы / Закрыть слот"
  - `/api/slots` учитывает `aria_availability` при генерации свободных окон
  - Блокировка конкретного слота (например, личные дела в 14:00)
  - Закрытие целого дня (отпуск, выходной)
  - Установка нестандартных часов на конкретную дату

- 🔲 **S3-C: Admin UI** — добавить/редактировать мастеров через owner-бот (новый раздел в menu.py)

- 🔲 **S3-D: Mini App шаг "Выбор мастера"** — вставить между Услугой и Датой

- 🔲 **S3-E: Dashboard по мастерам** — переключение в дашборде между мастерами, аналитика per-master

---

### S4 — Retention & Analytics (1-2 нед, только Python)

- 🔲 **S4-A: Auto-отзыв** — через 3ч после записи слать клиенту (если client_tg_id) кнопки ⭐1-5
  ```sql
  ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS review_sent BOOLEAN DEFAULT FALSE;
  CREATE TABLE aria_reviews (
      id BIGSERIAL PRIMARY KEY, tenant_id INT NOT NULL,
      booking_id BIGINT REFERENCES aria_bookings(id),
      master_id INT REFERENCES aria_masters(id),
      rating INT CHECK (rating BETWEEN 1 AND 5),
      text TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```

- 🔲 **S4-B: Import DM** — владелец пересылает скриншот/текст переписки из Instagram/WhatsApp,
  AI парсит имя + услугу + дату + время и создаёт запись через существующий `add_booking` tool

- 🔲 **S4-C: Monthly PNG отчёт** — 1го числа каждого месяца слать владельцу картинку с итогами
  (matplotlib → PNG → bot.send_photo). Метрики: выручка, число записей, топ-услуги, no-show %

---

## Как начать новую задачу

```
1. git checkout claude/telegram-booking-bot-research-cWjrw
2. git pull origin claude/telegram-booking-bot-research-cWjrw
3. Найди первый 🔲 пункт выше — это следующая задача
4. Реализуй, протестируй (python -c "import aria.main")
5. Обнови статус 🔲 → ✅ в этом файле
6. git add -A && git commit -m "feat: ..."
7. git push -u origin claude/telegram-booking-bot-research-cWjrw
```

## Как восстановить после поломки
```bash
git log --oneline -10
git checkout 230cc350c663c5b7ebd41bb283d16d0a776082ff  # v1.0.0 стабильный
```
