"""Punto de entrada ASGI. Se deja preparado aunque el despliegue use WSGI."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.produccion")

application = get_asgi_application()
