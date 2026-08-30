"""
Punto de entrada WSGI. Expone ``application``, que es lo que arranca gunicorn
en Render (ver ``render.yaml``).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.produccion")

application = get_wsgi_application()
