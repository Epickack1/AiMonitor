-- ==========================================
-- AIMonitor: структура базы данных
-- ==========================================

-- Разработчик модели: часть id OpenRouter до «/» (openai, anthropic, ...)
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

-- Модель ИИ. is_tracked = 0 — модель удалена из списка отслеживания,
-- но её проверки сохранились в истории.
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY,
    openrouter_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    vendor_id INTEGER NOT NULL,
    is_tracked INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
);

-- Результат проверки доступности модели.
-- uptime = NULL — OpenRouter не сообщил аптайм;
-- checked_at хранится строкой 'YYYY-MM-DD HH:MM' и сортируется как текст.
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    model_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    uptime REAL,
    checked_at TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id)
);
