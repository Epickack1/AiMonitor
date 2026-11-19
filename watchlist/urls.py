"""Маршруты отслеживаемых моделей.

id модели в OpenRouter содержит «/», например openai/gpt-4o-mini,
поэтому используется конвертер path: в отличие от str он пропускает «/».
"""

from django.urls import path

from . import views

app_name = "watchlist"

urlpatterns = [
    path("", views.models_list, name="list"),
    # Маршруты действий стоят перед detail: <path:...> принимает и «/»,
    # поэтому иначе «.../untrack/» попал бы в id модели.
    path("<path:model_id>/untrack/", views.model_untrack, name="untrack"),
    path("<path:model_id>/track/", views.model_track, name="track"),
    path("<path:model_id>/", views.model_detail, name="detail"),
]
