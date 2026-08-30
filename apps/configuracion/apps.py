"""Declaración de la app ``configuracion`` ante Django."""

from django.apps import AppConfig


class ConfiguracionPersonalizacion(AppConfig):
    """Campos personalizados, parámetros, etiquetas y vistas guardadas."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.configuracion"
    label = "configuracion"
    verbose_name = "Configuración"
