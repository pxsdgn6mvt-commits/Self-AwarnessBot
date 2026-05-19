# Aria Bot — Handoff для нового чата

## Репозиторий
Репо: `pxsdgn6mvt-commits/Self-AwarnessBot`  
Рабочая папка: `/home/user/Self-AwarnessBot`  
Активная ветка разработки: `claude/aria-voice-messages-7Jt8t`  
Стабильный снэпшот S1: `stable/s1-voice` (коммит `6dcb8d4`)

## Платформа
Railway — автодеплой из ветки `claude/aria-voice-messages-7Jt8t`.  
Деплой происходит автоматически при каждом `git push` в эту ветку.  
Перезапуск бота после деплоя не нужен — `/start` нажимать не нужно, бот подхватывает автоматически.

## Стек
- Python 3.11, aiogram 3.13.1, asyncpg, APScheduler
- Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) — AI чат с tool use
- OpenAI Whisper (`whisper-1`) — транскрипция голосовых сообщений
- PostgreSQL — всё состояние (FSM, история, брони, клиенты)
- Flask + Gunicorn — web-часть (лендинг)

## Переменные окружения (Railway → Variables)

| Переменная | Назначение |
|---|---|
| `ARIA_BOT_TOKEN` | Токен первого бота (seeds initial tenant) |
| `ANTHROPIC_API_KEY` | Ключ Anthropic |
| `ARIA_OWNER_TELEGRAM_ID` | Твой Telegram numeric ID (admin) |
| `DATABASE_URL` | PostgreSQL (Railway даёт автоматически) |
| `MANAGEMENT_BOT_TOKEN` | Токен @AriaReseptionist_Bot (admin bot) |
| `OPENAI_API_KEY` | **НОВОЕ в S1** — ключ OpenAI для Whisper транскрипции голоса |
| `GOOGLE_CALENDAR_CREDENTIALS` | Service account JSON (одной строкой) |

## Что работает (S1 — рабочая версия)

### Текстовый чат (AI)
- "запиши Катю на завтра на 2 часа дня" → AI вызывает `add_booking`, бот записывает
- AI сразу извлекает имя клиента из первого сообщения ("Запиши Вику..." → client_name="Вика")
- Rule-based bypass: "сегодня"/"завтра"/"ближайшие"/"эта неделя" без AI, без токенов

### Голосовые сообщения (S1 — новое)
- Пользователь отправляет голосовое → Whisper транскрибирует → AI обрабатывает
- Ответ: `🎙 «транскрипт»\n\nОтвет AI` — всё в одном сообщении
- Rate limit: 20 сообщений/мин
- При отключённом OPENAI_API_KEY: бот отвечает "Голосовые сообщения недоступны"

### Клавишное меню
- Сегодня / Завтра / Ближайшие / Новая запись / Дашборд / Меню — из любого FSM-состояния
- Guided booking wizard: категория → услуга → дата → время → имя клиента

### Google Calendar
- Брони создаются в GCal если настроен `/set_cal`
- Внешние брони (Yclients, Dikidi и т.д.) отображаются через GCal синк

### Email мониторинг
- IMAP polling каждые 5 мин → пересылка в Telegram

## Ключевые файлы

```
aria/
├── handlers/chat.py       ← catch-all handler: voice + text → AI
├── handlers/quick.py      ← reply keyboard, guided wizard, расписание
├── handlers/start.py      ← /start, /help, /reset, /set_cal, /set_tz
├── handlers/menu.py       ← inline меню, callback handlers
├── handlers/email_setup.py← email setup wizard
├── middleware.py          ← TenantMiddleware (cache + _last_good fallback)
├── services/ai.py         ← Claude Haiku + tool use
├── services/voice.py      ← Whisper транскрипция (НОВЫЙ в S1)
├── services/booking.py    ← LocalAdapter + GoogleAdapter
├── services/scheduler.py  ← APScheduler jobs
├── i18n.py               ← переводы (ru/en/fi)
├── config.py             ← читает env vars (в т.ч. OPENAI_API_KEY)
└── requirements.txt      ← зависимости (в т.ч. openai>=1.30.0)
```

## Известные ограничения / что НЕ работает

- Голосовые сообщения требуют `OPENAI_API_KEY` — без него фича отключена
- Бот owner-facing: не предназначен для прямого взаимодействия с клиентами салона
- FSM wizard не работает с голосовыми (голосовые в FSM-состоянии очищают state и уходят в AI)

## Что было в S1 (краткий лог)

1. Голосовые молча игнорировались (19ms, нет ответа):
   - FSM-обработчики ловили voice через `~F.text.in_(set)` (None not in set → True)
   - TenantMiddleware возвращал `tenant=None` при протухшем кеше
   - Фикс: добавлен `F.text` guard во все FSM-хендлеры; добавлен `_last_good` fallback
2. Bypass срабатывал для "запиши" (показывал расписание вместо брони):
   - "запиши" = зап+ИШ, "запись" = зап+ИС — разные корни
   - Фикс: добавлен `"запиш"` в `_BOOKING_VERBS`
3. AI не извлекал имя клиента из первого сообщения:
   - Фикс: добавлена секция "ЗАПИСЬ КЛИЕНТА" в system prompt
4. Echo и AI-ответ приходили двумя сообщениями:
   - Фикс: объединены в одно `f"{echo}\n\n{reply}"`

## Полная документация
Смотри `development.md` — полный reference по архитектуре, файлам, багам, деплою.
