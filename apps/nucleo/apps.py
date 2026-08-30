"""Declaración de la app ``nucleo`` ante Django."""

from django.apps import AppConfig


class ConfiguracionNucleo(AppConfig):
    """Usuarios, roles, permisos, almacenes y auditoría."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nucleo"
    label = "nucleo"
    verbose_name = "Núcleo"
