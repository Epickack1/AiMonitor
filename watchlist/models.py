"""Django-модели разработчиков и моделей ИИ.

Повторяют таблицы vendors и models из sql/schema.sql. Хранятся в служебной
базе Django (db.sqlite3) и заполняются из базы ПР7 командой
python manage.py import_pr7 или из JSON командой python manage.py import_json.
"""

from django.db import models
from django.db.models import Case, Value, When
from django.urls import reverse


class Vendor(models.Model):
    """Разработчик модели: часть id OpenRouter до «/»."""

    slug = models.SlugField(
        "код", max_length=50, unique=True,
        help_text="часть id OpenRouter до «/», например openai",
    )
    name = models.CharField("название", max_length=100)

    class Meta:
        verbose_name = "разработчик"
        verbose_name_plural = "разработчики"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """Адрес страницы разработчика по именованному маршруту."""
        return reverse("vendors:detail", kwargs={"slug": self.slug})


FREE_SUFFIX = ":free"


class AIModel(models.Model):
    """Модель ИИ. is_tracked = False — удалена из списка отслеживания."""

    openrouter_id = models.CharField("id в OpenRouter", max_length=200,
                                     unique=True)
    name = models.CharField("название", max_length=200)
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name="models",
        verbose_name="разработчик",
    )
    is_tracked = models.BooleanField("отслеживается", default=True)
    # Вычисляемый столбец: значение считает база данных при каждой записи
    # строки, приложение его не задаёт. db_persist=True — значение
    # хранится в таблице (STORED), а не вычисляется при каждом чтении.
    is_free = models.GeneratedField(
        expression=Case(
            When(openrouter_id__endswith=FREE_SUFFIX, then=Value(True)),
            default=Value(False),
        ),
        output_field=models.BooleanField(),
        db_persist=True,
        verbose_name="бесплатная",
    )

    class Meta:
        verbose_name = "модель ИИ"
        verbose_name_plural = "модели ИИ"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """Адрес страницы модели: id OpenRouter с «/» — конвертер path."""
        return reverse("watchlist:detail", args=[self.openrouter_id])
