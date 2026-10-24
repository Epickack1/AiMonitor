"""Главная страница и общий HTML-каркас всех страниц AIMonitor."""

from django.http import HttpResponse

from models.provider import (
    STATUS_AVAILABLE,
    STATUS_DOWN,
    STATUS_NOT_FOUND,
    STATUS_UNSTABLE,
)

BOOTSTRAP_CSS = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3"
    "/dist/css/bootstrap.min.css"
)

STATUS_BADGES = {
    STATUS_AVAILABLE: "bg-success",
    STATUS_UNSTABLE: "bg-warning text-dark",
    STATUS_DOWN: "bg-danger",
    STATUS_NOT_FOUND: "bg-secondary",
}


def status_badge(status: str) -> str:
    """Цветной бейдж Bootstrap со статусом модели."""
    css = STATUS_BADGES.get(status, "bg-secondary")
    return f'<span class="badge {css}">{status}</span>'


def page(title: str, content: str) -> str:
    """Собрать HTML-документ: кодировка, заголовок, Bootstrap, навигация."""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="stylesheet" href="{BOOTSTRAP_CSS}">
</head>
<body>
    <nav class="navbar navbar-expand bg-dark navbar-dark mb-4">
        <div class="container">
            <a class="navbar-brand" href="/">AIMonitor</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/models/">Модели</a>
                <a class="nav-link" href="/checks/">История проверок</a>
                <a class="nav-link" href="/checks/stats/">Статистика</a>
            </div>
        </div>
    </nav>
    <main class="container mb-5">{content}</main>
</body>
</html>"""


def index(request):
    """Главная страница: назначение приложения и переходы к разделам."""
    content = """
    <h1 class="display-5">AIMonitor</h1>
    <p class="lead">
        Мониторинг доступности моделей искусственного интеллекта
        в сервисе OpenRouter.
    </p>
    <p>
        Приложение показывает, какие из отслеживаемых моделей сейчас
        доступны, сколько провайдеров у каждой работает и каков их аптайм.
    </p>
    <a href="/models/" class="btn btn-primary me-2">Отслеживаемые модели</a>
    <a href="/checks/" class="btn btn-secondary me-2">История проверок</a>
    <a href="/checks/stats/" class="btn btn-outline-secondary">Статистика</a>
    """
    return HttpResponse(page("AIMonitor", content))


def page_not_found(request, exception):
    """Обработчик handler404: страница для адреса без маршрута."""
    content = """
    <h1 class="text-danger">404 – страница не найдена</h1>
    <p>Проверьте адрес или вернитесь на главную.</p>
    <a href="/" class="btn btn-primary">На главную</a>
    """
    return HttpResponse(
        page("404 – страница не найдена", content),
        status=404,
    )
