"""Rutas de la app ``movimientos`` — las completa Cristian."""

from django.urls import path

from apps.movimientos import views

app_name = "movimientos"

urlpatterns = [
    path("", views.indice, name="indice"),
    # TODO(Cristian): agregar aquí las rutas del módulo.
]
