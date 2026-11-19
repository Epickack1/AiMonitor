"""Django-модель результата проверки.

Повторяет таблицу checks из sql/schema.sql: каждая проверка ссылается
на модель ИИ внешним ключом.
"""

import datetime

from django.db import models

from models.provider import (
    STATUS_AVAILABLE,
    STATUS_DOWN,
    STATUS_NOT_FOUND,
    STATUS_UNSTABLE,
)
from watchlist.models import AIModel


class CheckQuerySet(models.QuerySet):
    """Повторяющиеся условия выборки проверок.

    Методы возвращают QuerySet, поэтому их можно соединять в цепочку:
    Check.objects.for_date(day).available().
    """

    def available(self):
        """Успешные проверки: модель была доступна."""
        return self.filter(status=Check.Status.AVAILABLE)

    def failed(self):
        """Неуспешные проверки: все, кроме успешных."""
        return self.exclude(status=Check.Status.AVAILABLE)

    def for_date(self, day: datetime.date):
        """Проверки за календарный день в часовом поясе TIME_ZONE."""
        return self.filter(checked_at__date=day)

    def for_vendor(self, slug: str):
        """Проверки моделей одного разработчика."""
        return self.filter(model__vendor__slug=slug)


class Check(models.Model):
    """Результат проверки. uptime = None — OpenRouter не сообщил аптайм."""

    class Status(models.TextChoices):
        """Статус проверки: код хранится в базе, подпись показывается.

        Подписи совпадают со статусами консольной версии (models/provider.py),
        поэтому статус из JSON переводится в код словарём STATUS_BY_LABEL.
        """

        AVAILABLE = "available", STATUS_AVAILABLE
        UNSTABLE = "unstable", STATUS_UNSTABLE
        DOWN = "down", STATUS_DOWN
        NOT_FOUND = "not_found", STATUS_NOT_FOUND

    model = models.ForeignKey(
        AIModel,
        on_delete=models.CASCADE,
        related_name="checks",
        verbose_name="модель",
    )
    status = models.CharField("статус", max_length=20,
                              choices=Status.choices)
    uptime = models.FloatField("аптайм, %", null=True, blank=True)
    checked_at = models.DateTimeField("время проверки")

    objects = CheckQuerySet.as_manager()

    class Meta:
        verbose_name = "проверка"
        verbose_name_plural = "проверки"
        ordering = ["-checked_at", "-id"]

    def __str__(self) -> str:
        return f"{self.model} — {self.get_status_display()}"


# Подпись статуса консольной версии → код Check.Status
STATUS_BY_LABEL = {label: value for value, label in Check.Status.choices}
