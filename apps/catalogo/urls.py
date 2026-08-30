"""Rutas de la app ``catalogo`` — las completa Arturo."""

from django.urls import path

from apps.catalogo import views

app_name = "catalogo"

urlpatterns = [
    path("", views.indice, name="indice"),
    # TODO(Arturo): agregar aquí las rutas del módulo.
]
