"""Маршруты отслеживаемых моделей.

id модели в OpenRouter содержит «/», например openai/gpt-4o-mini,
поэтому используется конвертер path: в отличие от str он пропускает «/».
"""

from django.urls import path

from . import views

app_name = "watchlist"

urlpatterns = [
    path("", views.models_list, name="list"),
    path("<path:model_id>/", views.model_detail, name="detail"),
]
