"""Declaración de la app ``catalogo`` ante Django."""

from django.apps import AppConfig


class ConfiguracionCatalogo(AppConfig):
    """Artículos, categorías, unidades de medida y existencias."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalogo"
    label = "catalogo"
    verbose_name = "Catálogo"
