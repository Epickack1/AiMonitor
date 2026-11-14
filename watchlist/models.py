"""Django-модели разработчиков и моделей ИИ.

Повторяют таблицы vendors и models из sql/schema.sql. Хранятся в служебной
базе Django (db.sqlite3) и заполняются из базы ПР7 командой
python manage.py import_pr7 или из JSON командой python manage.py import_json.
"""

from django.db import models


class Vendor(models.Model):
    """Разработчик модели: часть id OpenRouter до «/»."""

    slug = models.CharField("код", max_length=50, unique=True)
    name = models.CharField("название", max_length=100)

    class Meta:
        verbose_name = "разработчик"
        verbose_name_plural = "разработчики"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


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

    class Meta:
        verbose_name = "модель ИИ"
        verbose_name_plural = "модели ИИ"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_free(self) -> bool:
        """Бесплатная модель: id в OpenRouter оканчивается на «:free»."""
        return self.openrouter_id.endswith(FREE_SUFFIX)
