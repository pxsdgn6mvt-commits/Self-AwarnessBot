# Sprint 008 — Acceptance Criteria

## Must Pass
- [ ] Кнопка 👥 Мастера в _owner_settings_kb(), callback_data="cfg:masters"
- [ ] aria/handlers/masters.py существует
- [ ] cfg:masters показывает список с именем, телефоном, статусом
- [ ] Для активного — кнопка деактивации; для деактивированного — реактивации
- [ ] cfg:master_off:{id} деактивирует с confirm
- [ ] cfg:master_on:{id} реактивирует без confirm
- [ ] cfg:master_add запускает FSM: имя → телефон → создаёт мастера
- [ ] Телефон пропускаемый (/skip или аналог)
- [ ] После добавления — обновлённый список
- [ ] masters_router зарегистрирован в диспетчере
- [ ] repo.py содержит set_master_active()
- [ ] Кнопка ← Назад возвращает в Settings

## Should Pass
- [ ] Мастер-владелец помечен 👑
- [ ] Деактивация владельца заблокирована
- [ ] Список обновляется после каждого действия

## NOT Checked
- Привязка услуг (Sprint 009)
- Mini App изменения (Sprint 010)
