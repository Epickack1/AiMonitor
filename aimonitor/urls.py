"""Маршрутизация верхнего уровня: адреса распределяются по приложениям."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("homepage.urls")),
    path("models/", include("watchlist.urls")),
    path("vendors/", include("watchlist.vendor_urls")),
    path("checks/", include("checks.urls")),
]

# Раздача загруженных файлов сервером разработки. В рабочем режиме
# медиафайлы раздаёт веб-сервер, а не Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)

if settings.DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()

# Собственная страница 404: действует для всех приложений при DEBUG = False.
handler404 = "homepage.views.page_not_found"
