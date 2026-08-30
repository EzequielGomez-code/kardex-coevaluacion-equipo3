"""Rutas de la app ``configuracion``."""

from django.urls import path

from apps.configuracion import views

app_name = "configuracion"

urlpatterns = [
    path("parametros/", views.parametros, name="parametros"),
    path("campos/", views.campos, name="campos"),
    path("campos/nuevo/", views.campo_formulario, name="campo_nuevo"),
    path("campos/<int:definicion_id>/editar/", views.campo_formulario, name="campo_editar"),
    path("campos/reordenar/", views.campos_reordenar, name="campos_reordenar"),
    path("etiquetas/", views.etiquetas, name="etiquetas"),
    path("etiquetas/nueva/", views.etiqueta_formulario, name="etiqueta_nueva"),
    path("etiquetas/<int:etiqueta_id>/editar/", views.etiqueta_formulario,
         name="etiqueta_editar"),
    path("etiquetas/<int:etiqueta_id>/alternar/", views.etiqueta_alternar,
         name="etiqueta_alternar"),
]
