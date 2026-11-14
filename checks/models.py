"""Django-модель результата проверки.

Повторяет таблицу checks из sql/schema.sql: каждая проверка ссылается
на модель ИИ внешним ключом.
"""

from django.db import models

from models.provider import (
    STATUS_AVAILABLE,
    STATUS_DOWN,
    STATUS_NOT_FOUND,
    STATUS_UNSTABLE,
)
from watchlist.models import AIModel

STATUS_CHOICES = [
    (status, status)
    for status in (
        STATUS_AVAILABLE,
        STATUS_UNSTABLE,
        STATUS_DOWN,
        STATUS_NOT_FOUND,
    )
]


class Check(models.Model):
    """Результат проверки. uptime = None — OpenRouter не сообщил аптайм."""

    model = models.ForeignKey(
        AIModel,
        on_delete=models.CASCADE,
        related_name="checks",
        verbose_name="модель",
    )
    status = models.CharField("статус", max_length=20,
                              choices=STATUS_CHOICES)
    uptime = models.FloatField("аптайм, %", null=True, blank=True)
    checked_at = models.DateTimeField("время проверки")

    class Meta:
        verbose_name = "проверка"
        verbose_name_plural = "проверки"
        ordering = ["-checked_at", "-id"]

    def __str__(self) -> str:
        return f"{self.model} — {self.status}"
