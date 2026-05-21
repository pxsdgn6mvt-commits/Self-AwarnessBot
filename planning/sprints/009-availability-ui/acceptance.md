# Sprint 009 — Acceptance Criteria

## Must Pass
- [ ] Кнопка 📅 Расписание есть в списке мастеров (cfg:avail:{id})
- [ ] cfg:avail:{id} показывает главный экран с 4 кнопками действий
- [ ] cfg:avail_close:{id} запускает FSM закрытия дня
- [ ] FSM закрытия: дата → confirm → INSERT is_open=FALSE
- [ ] cfg:avail_hours:{id} запускает FSM изменения часов
- [ ] FSM часов: дата → часы (формат ЧЧ-ЧЧ) → confirm → INSERT is_open=TRUE
- [ ] cfg:avail_slot:{id} запускает FSM блокировки слота
- [ ] FSM слота: дата → время → confirm → INSERT is_open=FALSE
- [ ] time_to в FSM слота = time_from + slot_minutes из aria_tenants
- [ ] cfg:avail_list:{id} показывает блокировки с date >= today
- [ ] cfg:avail_del:{avail_id} удаляет блокировку, показывает обновлённый список
- [ ] repo.py содержит create_availability()
- [ ] repo.py содержит get_availability()
- [ ] repo.py содержит delete_availability()
- [ ] repo.py содержит get_tenant_slot_minutes()
- [ ] availability_router зарегистрирован в диспетчере

## Should Pass
- [ ] Валидация даты: не в прошлом, понятное сообщение об ошибке
- [ ] Валидация часов: from < to, в пределах 0-23
- [ ] Валидация времени слота: в пределах рабочих часов тенанта
- [ ] При невалидном вводе FSM остаётся в том же state (не ломается)
- [ ] Список блокировок отсортирован по date ASC
- [ ] Тип блокировки визуально различим (🔴 день / 🕐 часы / ⛔ слот)

## NOT Checked
- /api/slots учитывает aria_availability (Sprint 010)
- Master-bot UI (Sprint 011)
- miniapp/ изменения
