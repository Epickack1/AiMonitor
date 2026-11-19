"""Маршруты истории проверок, статистики и формы проверки."""

from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "checks"

urlpatterns = [
    path("", views.history, name="history"),
    path("stats/", views.stats, name="stats"),
    path("new/", views.check_create, name="create"),
    path("<int:pk>/", views.check_detail, name="detail"),
    path("<int:pk>/edit/", views.check_edit, name="edit"),
    # Поиск проверок из первой версии ПР9 объединён с историей:
    # старый адрес ведёт на /checks/ с теми же параметрами.
    path(
        "search/",
        RedirectView.as_view(pattern_name="checks:history",
                             query_string=True),
        name="search",
    ),
]
