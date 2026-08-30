"""Declaración de la app ``alertas`` ante Django."""

from django.apps import AppConfig


class ConfiguracionAlertas(AppConfig):
    """Reglas de alerta, notificaciones y proveedores."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alertas"
    label = "alertas"
    verbose_name = "Alertas"
