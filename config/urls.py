"""
Rutas raíz de Kardex.

Cada app cuelga su propio ``urls.py`` bajo un prefijo. Los compañeros que
construyen catálogo, movimientos y alertas solo tienen que llenar el suyo:
esta tabla ya los incluye.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("panel-django/", admin.site.urls),
    path("", include(("apps.nucleo.urls", "nucleo"), namespace="nucleo")),
    path(
        "configuracion/",
        include(("apps.configuracion.urls", "configuracion"), namespace="configuracion"),
    ),
    path("catalogo/", include(("apps.catalogo.urls", "catalogo"), namespace="catalogo")),
    path(
        "movimientos/",
        include(("apps.movimientos.urls", "movimientos"), namespace="movimientos"),
    ),
    path("alertas/", include(("apps.alertas.urls", "alertas"), namespace="alertas")),
]

# Los archivos subidos solo se sirven desde Django en desarrollo.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Páginas de error propias, con el mismo layout que el resto del sistema.
handler403 = "apps.nucleo.views.error_403"
handler404 = "apps.nucleo.views.error_404"
handler500 = "apps.nucleo.views.error_500"
