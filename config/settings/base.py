"""
Ajustes base de Kardex, compartidos por todos los entornos.

Todo secreto se lee de variables de entorno con ``django-environ``; en el
repositorio solo se versiona ``.env.ejemplo`` sin valores reales.
Referencia de seguridad: punto 6.5 del brief (OWASP A05 — Mala configuración).
"""

from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
# base.py -> settings -> config -> raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

# Lee el archivo .env local si existe. En Render las variables llegan del entorno.
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
# Seguridad #5: la clave nunca vive en el código.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="clave-insegura-solo-para-desarrollo")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Terceros
    "axes",
    # Propias
    "apps.nucleo",
    "apps.configuracion",
    "apps.catalogo",
    "apps.movimientos",
    "apps.alertas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sirve los estáticos sin S3 ni CDN (punto 7 del brief).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Registra en la auditoría quién hace cada cambio (Seguridad #8).
    "apps.nucleo.middleware.MiddlewareUsuarioActual",
    # Reencauza al modal los errores de formulario que hx-swap="none" descartaría.
    "apps.nucleo.middleware.MiddlewareReenfocarErroresDeModal",
    # Axes va de último para ver la petición ya autenticada (Seguridad #7).
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

# Las carpetas de plantillas de las apps se llaman «plantillas», no «templates»,
# así que se listan a mano. ``APP_DIRS`` sigue encendido para que el panel de
# administración de Django encuentre las suyas.
DIRECTORIOS_PLANTILLAS = [BASE_DIR / "plantillas"] + sorted(
    (BASE_DIR / "apps").glob("*/plantillas")
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": DIRECTORIOS_PLANTILLAS,
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Menú lateral, parámetros del sistema y versión en el pie.
                "apps.nucleo.contexto.navegacion_lateral",
                "apps.nucleo.contexto.datos_de_version",
                "apps.configuracion.contexto.parametros_del_sistema",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos: un solo DATABASE_URL decide entre SQLite y PostgreSQL (Neon)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Autenticación y contraseñas
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "nucleo.Usuario"

# Seguridad #1: Argon2 primero. Los demás quedan para verificar hashes antiguos.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Seguridad #7: django-axes bloquea tras 5 intentos fallidos durante 30 minutos.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5  # en horas = 30 minutos
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/bloqueado.html"

LOGIN_URL = "nucleo:iniciar_sesion"
LOGIN_REDIRECT_URL = "nucleo:panel"
LOGOUT_REDIRECT_URL = "nucleo:iniciar_sesion"

# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es-do"
TIME_ZONE = env("TIME_ZONE", default="America/Santo_Domingo")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos y subidos
# ---------------------------------------------------------------------------
STATIC_URL = "estaticos/"
STATICFILES_DIRS = [BASE_DIR / "estaticos"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "medios/"
MEDIA_ROOT = BASE_DIR / "medios"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Seguridad #11: tope de tamaño y extensiones permitidas en subidas.
TAMANO_MAXIMO_ARCHIVO_MB = env.int("TAMANO_MAXIMO_ARCHIVO_MB", default=5)
EXTENSIONES_PERMITIDAS = ["pdf", "png", "jpg", "jpeg", "webp", "csv", "xlsx"]
DATA_UPLOAD_MAX_MEMORY_SIZE = TAMANO_MAXIMO_ARCHIVO_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

# ---------------------------------------------------------------------------
# Sesiones, CSRF y cabeceras (Seguridad #2 y #6)
# ---------------------------------------------------------------------------
CSRF_COOKIE_HTTPONLY = False  # HTMX lee el token de la cookie para reenviarlo
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_AGE = 60 * 60 * 8  # una jornada de trabajo
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# ---------------------------------------------------------------------------
# Registro de eventos
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {
        "kardex": {"handlers": ["consola"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Datos propios de Kardex
# ---------------------------------------------------------------------------
VERSION_KARDEX = "0.1.0"
NOMBRE_SISTEMA = "Kardex"
NOMBRE_EMPRESA = "Ferretería M y F, S.R.L."

# Contraseña del administrador que crea «manage.py sembrar». Si queda vacía, el
# comando genera una al azar y la muestra una sola vez (Seguridad #5).
CONTRASENA_ADMIN_INICIAL = env("DJANGO_ADMIN_PASSWORD", default="")
