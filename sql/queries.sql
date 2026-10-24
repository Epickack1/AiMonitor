-- ==========================================
-- AIMonitor: SQL-запросы проекта
-- ==========================================
-- Проверка: sqlite3 data/aimonitor.sqlite
-- Конкретные значения ('qwen', '2026-09-26', ...) подставлены для проверки
-- в SQLite CLI. В Django-представлениях они передаются параметрами ? / :имя.


-- ------------------------------------------
-- Выборка списков
-- ------------------------------------------

-- 1. Отслеживаемые модели в порядке добавления
-- (страница /models/ без сортировки)
SELECT
    id,
    openrouter_id,
    name
FROM models
WHERE is_tracked = 1
ORDER BY id;

-- 2. Отслеживаемые модели по названию без учёта регистра
-- (страница /models/?sort=name)
SELECT
    id,
    openrouter_id,
    name
FROM models
WHERE is_tracked = 1
ORDER BY name COLLATE NOCASE;

-- 3. Даты, за которые есть проверки, — варианты фильтра истории
SELECT DISTINCT
    substr(checked_at, 1, 10) AS day
FROM checks
ORDER BY day DESC;


-- ------------------------------------------
-- Фильтрация WHERE
-- ------------------------------------------

-- 4. Поиск модели по подстроке в id или названии
-- (страница /models/?q=qwen)
SELECT
    openrouter_id,
    name
FROM models
WHERE is_tracked = 1
  AND (openrouter_id LIKE '%qwen%' OR name LIKE '%qwen%')
ORDER BY id;

-- 5. Бесплатные модели: id оканчивается на :free
-- (страница /models/?free=1)
SELECT
    openrouter_id,
    name
FROM models
WHERE is_tracked = 1
  AND openrouter_id LIKE '%:free'
ORDER BY id;

-- 6. Последние 10 проверок одной модели, новые сверху
-- (страница /models/openai/gpt-4o-mini/)
SELECT
    checks.checked_at,
    checks.status,
    checks.uptime
FROM checks
JOIN models
    ON checks.model_id = models.id
WHERE models.openrouter_id = 'openai/gpt-4o-mini'
ORDER BY checks.id DESC
LIMIT 10;


-- ------------------------------------------
-- Соединение таблиц JOIN
-- ------------------------------------------

-- 7. Модель и её разработчик по id OpenRouter
-- (карточка на странице модели)
SELECT
    models.openrouter_id,
    models.name,
    models.is_tracked,
    vendors.name AS vendor_name
FROM models
JOIN vendors
    ON models.vendor_id = vendors.id
WHERE models.openrouter_id = 'openai/gpt-4o-mini';

-- 8. Отслеживаемые модели с результатом последней проверки
-- (таблица на странице /models/). LEFT JOIN оставляет модели
-- без проверок, у них поля проверки равны NULL.
SELECT
    models.openrouter_id,
    models.name,
    checks.status,
    checks.uptime,
    checks.checked_at
FROM models
LEFT JOIN checks
    ON checks.id = (
        SELECT MAX(last.id)
        FROM checks AS last
        WHERE last.model_id = models.id
    )
WHERE models.is_tracked = 1
ORDER BY checks.uptime IS NULL, checks.uptime DESC, models.id;

-- 9. История проверок с названиями моделей за выбранный день
-- и с выбранным статусом (страница /checks/?day=2026-09-26&status=...)
SELECT
    checks.checked_at,
    checks.status,
    checks.uptime,
    models.openrouter_id,
    models.name AS model_name
FROM checks
JOIN models
    ON checks.model_id = models.id
WHERE substr(checks.checked_at, 1, 10) = '2026-09-26'
  AND checks.status = 'Доступна'
ORDER BY checks.id DESC
LIMIT 100;


-- ------------------------------------------
-- Агрегатные функции
-- ------------------------------------------

-- 10. Сводка для главной страницы: моделей, проверок, последняя проверка
SELECT
    (SELECT COUNT(*) FROM models WHERE is_tracked = 1) AS models_count,
    COUNT(*) AS checks_count,
    MAX(checked_at) AS last_checked_at
FROM checks;

-- 11. Сводка по одной модели: число проверок, доля успешных,
-- средний аптайм (AVG не учитывает NULL)
SELECT
    COUNT(*) AS checks_count,
    ROUND(100.0 * SUM(checks.status = 'Доступна') / COUNT(*), 1) AS percent,
    AVG(checks.uptime) AS avg_uptime
FROM checks
JOIN models
    ON checks.model_id = models.id
WHERE models.openrouter_id = 'openai/gpt-4o-mini';


-- ------------------------------------------
-- Группировка GROUP BY и фильтрация групп HAVING
-- ------------------------------------------

-- 12. Статистика доступности каждой модели — от самой стабильной
-- к самой проблемной (страница /checks/stats/)
SELECT
    models.openrouter_id,
    models.name,
    COUNT(checks.id) AS checks_count,
    ROUND(100.0 * SUM(checks.status = 'Доступна') / COUNT(checks.id), 1)
        AS percent,
    AVG(checks.uptime) AS avg_uptime
FROM models
JOIN checks
    ON checks.model_id = models.id
GROUP BY models.id, models.openrouter_id, models.name
ORDER BY percent DESC, COALESCE(avg_uptime, 0) DESC, models.openrouter_id;

-- 13. Проблемные модели: хотя бы одна проверка была неуспешной
SELECT
    models.openrouter_id,
    models.name,
    COUNT(checks.id) AS checks_count,
    COUNT(checks.id) - SUM(checks.status = 'Доступна') AS failed_count
FROM models
JOIN checks
    ON checks.model_id = models.id
GROUP BY models.id, models.openrouter_id, models.name
HAVING SUM(checks.status = 'Доступна') < COUNT(checks.id)
ORDER BY failed_count DESC, models.openrouter_id;

-- 14. Количество проверок с каждым статусом
SELECT
    status,
    COUNT(*) AS checks_count
FROM checks
GROUP BY status
ORDER BY checks_count DESC;

-- 15. Разработчики: сколько моделей отслеживается и сколько
-- проверок выполнено. LEFT JOIN оставляет модели без проверок.
SELECT
    vendors.name AS vendor_name,
    COUNT(DISTINCT models.id) AS models_count,
    COUNT(checks.id) AS checks_count
FROM vendors
JOIN models
    ON models.vendor_id = vendors.id
LEFT JOIN checks
    ON checks.model_id = models.id
WHERE models.is_tracked = 1
GROUP BY vendors.id, vendors.name
ORDER BY models_count DESC, vendor_name;
