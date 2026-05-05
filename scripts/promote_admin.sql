-- Назначить пользователя админом по Telegram ID.
-- 1) Узнай свой числовой id (например @userinfobot или лог бота при /start).
-- 2) Подставь его вместо 943071273 ниже.
-- 3) Выполни в psql / SQL Editor (Supabase) под своей БД.
--
-- Роли в коде: user | admin | owner | tester
-- Для «полного» владельца можно использовать 'owner' вместо 'admin'.

BEGIN;

UPDATE users
SET role = 'admin'
WHERE telegram_id = 943071273;

-- Должно быть UPDATE 1. Если 0 — пользователь ещё не заходил в бота (нет строки в users).

SELECT id, telegram_id, username, role, plan, is_blocked
FROM users
WHERE telegram_id = 943071273;

COMMIT;
