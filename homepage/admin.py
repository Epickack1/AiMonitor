"""Заголовки админ-панели: русские названия вместо «Django administration»."""

from django.contrib import admin

admin.site.site_header = "AIMonitor — администрирование"
admin.site.site_title = "AIMonitor"
admin.site.index_title = "Данные мониторинга моделей ИИ"
