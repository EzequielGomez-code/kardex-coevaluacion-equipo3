"""
Ajustes de desarrollo local.

Se usan cuando ``DJANGO_SETTINGS_MODULE=config.settings.local``. Nunca deben
usarse en el servidor público: aquí ``DEBUG`` puede quedar encendido.
"""

# pylint: disable=wildcard-import,unused-wildcard-import
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# En local no hay HTTPS, así que las cookies seguras romperían el inicio de sesión.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Los estáticos se sirven sin manifiesto para no tener que correr collectstatic
# en cada cambio de CSS.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Axes desactivado en las pruebas automáticas para que no bloquee al usuario
# de prueba tras varios intentos deliberadamente fallidos.
AXES_ENABLED = env.bool("AXES_ENABLED", default=True)
