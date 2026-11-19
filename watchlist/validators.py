"""Валидаторы загружаемых файлов."""

from django.core.exceptions import ValidationError

MAX_LOGO_SIZE = 2 * 1024 * 1024


def validate_logo_size(file):
    """Логотип не больше 2 МБ: большие файлы не нужны для значка."""
    if file.size > MAX_LOGO_SIZE:
        raise ValidationError(
            "Файл больше 2 МБ. Загрузите изображение меньшего размера.",
            code="file_too_large",
        )
