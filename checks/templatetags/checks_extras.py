"""Фильтры шаблонов для проверок."""

from django import template

from checks.models import Check

register = template.Library()


@register.filter
def status_label(code):
    """Код статуса (available) → подпись для пользователя (Доступна)."""
    if code in Check.Status.values:
        return Check.Status(code).label
    return code
