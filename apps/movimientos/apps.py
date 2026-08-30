"""Declaración de la app ``movimientos`` ante Django."""

from django.apps import AppConfig


class ConfiguracionMovimientos(AppConfig):
    """Entradas, salidas, transferencias y el kardex valorado."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.movimientos"
    label = "movimientos"
    verbose_name = "Movimientos"
