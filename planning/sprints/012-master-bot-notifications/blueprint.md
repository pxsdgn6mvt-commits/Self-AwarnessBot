Sprint 012 — Blueprint

Corrected Architecture

Tenant-бот уже работает через _watch_tenants() в main.py.
Там хранится dict активных ботов. Нужно:

	1.	Сделать этот dict доступным для notifications.py
	2.	Для получения tg_id владельца — читать из aria_tenants по tenant_id
	3.	Вызывать уведомление после каждой записи-мутации

Files to Modify

1. aria/main.py

	•	Найти dict активных tenant-ботов внутри _watch_tenants() (или на уровне модуля)
	•	Добавить публичный accessor: def get_tenant_bot(tenant_id: int) -> Bot | None
	•	Если dict уже module-level — просто добавить функцию-обёртку

2. aria/notifications.py ← NEW FILE

Три async-функции:

async def notify_owner_new_booking(tenant_id, owner_tg_id, client_name,
    client_phone, service_name, dt: datetime) -> None

async def notify_owner_cancelled(tenant_id, owner_tg_id, client_name,
    service_name, dt: datetime) -> None

async def notify_owner_rescheduled(tenant_id, owner_tg_id, client_name,
    service_name, old_dt: datetime, new_dt: datetime) -> None


Каждая функция:

	•	Вызывает get_tenant_bot(tenant_id) → если None, silent return
	•	bot.send_message(owner_tg_id, text) в try/except TelegramAPIError
	•	Логирует успех и ошибку через logging

3. aria/db/repo.py

Три точки внедрения (реальные имена функций из кодовой базы):



|Blueprint (ошибочно)|Реальная функция                        |Действие                                 |
|--------------------|----------------------------------------|-----------------------------------------|
|`create_booking()`  |`create_booking()` ✅                    |после INSERT → `notify_owner_new_booking`|
|`delete_booking()`  |`update_booking_status(id, 'cancelled')`|после UPDATE → `notify_owner_cancelled`  |
|`update_booking()`  |`update_booking_time(id, new_time)`     |после UPDATE → `notify_owner_rescheduled`|

Для каждой точки:

	•	Получить tenant_id (уже есть в аргументах или в результате SELECT)
	•	Получить owner_tg_id из aria_tenants — добавить хелпер
get_tenant_owner_tg_id(tenant_id) -> int | None если его нет
	•	Вызвать asyncio.create_task(notify_owner_*(...))

4. aria/db/repo.py — новый хелпер (если отсутствует)

async def get_tenant_owner_tg_id(tenant_id: int) -> int | None:
    # SELECT tg_id FROM aria_tenants WHERE id = $1


Перед реализацией — проверить, есть ли уже функция возвращающая tg_id тенанта.

5. aria/db/repo.py — хелпер для деталей записи

async def get_booking_details(booking_id: int) -> dict | None:
    # JOIN aria_bookings + aria_clients + aria_service_items
    # Возвращает: client_name, client_phone, service_name, dt, tenant_id


Перед реализацией — проверить, есть ли уже аналогичная функция.

6. tests/test_notifications.py ← NEW FILE

5 тестов с AsyncMock. Патчить aria.notifications.get_tenant_bot.

Import Chain (acyclic)

main.py → (ничего из notifications)
notifications.py → main.get_tenant_bot
repo.py → notifications.notify_*
main.py → repo (уже есть)


Цикла нет.

Implementation Order

	1.	main.py — get_tenant_bot()
	2.	notifications.py — три функции
	3.	repo.py — хелперы + три точки внедрения
	4.	tests/test_notifications.py
