"""
Ajustes de producción (Render + Neon).

Aplica el punto 6.6 del brief: ``DEBUG`` apagado, hosts cerrados, HTTPS
obligatorio y cookies seguras. Corresponde a OWASP A05 (Mala configuración)
y A02 (Fallas criptográficas: tránsito cifrado).
"""

# pylint: disable=wildcard-import,unused-wildcard-import
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Render (Oregón) y Neon (us-east-2) están en regiones distintas: abrir una
# conexión nueva cuesta un ida y vuelta caro. Se sostienen diez minutos en vez
# de uno, apoyadas en CONN_HEALTH_CHECKS de base.py, que es lo que hace seguro
# reutilizarlas.
DATABASES["default"]["CONN_MAX_AGE"] = 600  # noqa: F405

# ALLOWED_HOSTS cerrado: se declara explícitamente en el entorno de Render.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Render expone el host público del servicio en esta variable.
NOMBRE_HOST_RENDER = env("RENDER_EXTERNAL_HOSTNAME", default="")
if NOMBRE_HOST_RENDER:
    ALLOWED_HOSTS.append(NOMBRE_HOST_RENDER)

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if NOMBRE_HOST_RENDER:
    CSRF_TRUSTED_ORIGINS.append("https://" + NOMBRE_HOST_RENDER)

# Seguridad #6: HTTPS obligatorio y cookies que no viajan en claro.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000  # un año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
