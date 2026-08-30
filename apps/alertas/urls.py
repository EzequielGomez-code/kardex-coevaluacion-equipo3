"""Rutas de la app ``alertas`` — las completa Francisco."""

from django.urls import path

from apps.alertas import views

app_name = "alertas"

urlpatterns = [
    path("", views.indice, name="indice"),
    # TODO(Francisco): agregar aquí las rutas del módulo.
]
