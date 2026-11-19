"""Валидаторы полей проверки: функции, которые поднимают ValidationError."""

from django.core.exceptions import ValidationError
from django.utils import timezone


def validate_not_in_future(value):
    """Время проверки не может быть позже текущего момента."""
    if value > timezone.now():
        raise ValidationError(
            "Время проверки не может быть в будущем.", code="future"
        )
