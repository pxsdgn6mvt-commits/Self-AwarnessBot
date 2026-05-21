# Sprint 002 — Blueprint

## Files to Modify

### 1. `aria/handlers/menu.py` (или подходящий хендлер)
Найти хендлер команды /start (или главного меню клиента).
Добавить кнопку типа WebAppInfo:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import os

MINIAPP_URL = os.getenv("MINIAPP_URL", "")

# В хендлере клиента:
webapp_url = f"{MINIAPP_URL}?tenant_id={tenant.id}"

keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(
        text="📅 Записаться",
        web_app=WebAppInfo(url=webapp_url)
    )
]])
await message.answer("Выберите действие:", reply_markup=keyboard)
```

Найти правильную точку вставки через существующий код — не создавать
новый хендлер если подходящий уже есть.

### 2. `server.py` — эндпоинт `/api/services`
Добавить поле `working_days` в JSON-ответ:

```python
# В ответ /api/services добавить на уровне тенанта:
"working_days": tenant_row["working_days"]  # тип взять из реальной модели
```

Прочитать DOMAIN.md чтобы понять тип поля `working_days` перед написанием.

### 3. `miniapp/src/screens/DateScreen.tsx`
Получить `working_days` из ответа `/api/services` (он уже вызывается
при инициализации — проверить существующий код).
Добавить фильтр в логику генерации дат:

```typescript
// Псевдокод — адаптировать под реальную структуру компонента:
const isWorkingDay = (date: Date): boolean => {
  const day = date.getDay(); // 0=Sun, 1=Mon, ...
  return workingDays.includes(day); // тип working_days уточнить из ответа API
};

// При генерации списка дат — добавить фильтр нерабочих дней
```

Не переписывать компонент — только добавить фильтр в существующую логику.

---

## Files to Create
Никаких новых файлов не создавать.

---

## Manual Step (не автоматизируется Builder'ом)
После завершения спринта человек выполняет вручную:

1. В Cloudflare Pages → Settings → Environment Variables
2. Добавить: `VITE_API_BASE = https://<railway-web-service-url>`
3. Trigger new deploy (или push пустой коммит)
4. Проверить что `api.ts` подхватывает переменную

Builder должен добавить этот шаг в итоговый summary.

---

## Reading Order for Builder

1. `development.md` — секции "2. Architecture", "6. File-by-File Reference"
2. `docs/DOMAIN.md` — поле `working_days` тенанта
3. `docs/DECISIONS.md` — убедиться нет решений против WebApp-кнопки
4. `docs/STATE.md` — подтвердить текущий статус S2-C
5. `aria/handlers/menu.py` — найти точку вставки кнопки
6. `server.py` — найти `/api/services` эндпоинт
7. `miniapp/src/screens/DateScreen.tsx` — найти логику генерации дат
8. `miniapp/src/api.ts` — подтвердить `VITE_API_BASE` проблему
