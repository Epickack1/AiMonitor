"""Конфигурация pytest: корень проекта попадает в sys.path.

Для тестов веб-страниц подключаются настройки Django и тестовое окружение:
setup_test_environment() разрешает тестовому клиенту хост testserver.
"""

import os

import django
from django.test.utils import setup_test_environment

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aimonitor.settings")
django.setup()
setup_test_environment()
