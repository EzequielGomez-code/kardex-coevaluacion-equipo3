"""Rutas de la app ``alertas``."""

from django.urls import path

from apps.alertas import views

app_name = "alertas"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("evaluar/", views.evaluar_ahora, name="evaluar_ahora"),
    path("<int:alerta_id>/estado/", views.alerta_cambiar_estado, name="alerta_estado"),
    path("reglas/", views.reglas, name="reglas"),
    path("reglas/nueva/", views.regla_formulario, name="regla_nueva"),
    path("reglas/<int:regla_id>/editar/", views.regla_formulario, name="regla_editar"),
]
