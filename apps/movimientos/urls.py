"""Rutas de la app ``movimientos``."""

from django.urls import path

from apps.movimientos import views

app_name = "movimientos"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("existencias/", views.existencias, name="existencias"),
    path("aprobaciones/", views.aprobaciones, name="aprobaciones"),
    path("aprobaciones/<int:movimiento_id>/aprobar/", views.movimiento_aprobar, name="aprobar"),
    path("aprobaciones/<int:movimiento_id>/rechazar/", views.movimiento_rechazar, name="rechazar"),
    path("kardex/<int:articulo_id>/", views.kardex, name="kardex"),
    path("entradas/nueva/", views.entrada_formulario, name="entrada_nueva"),
    path("salidas/nueva/", views.salida_formulario, name="salida_nueva"),
    path("transferencias/nueva/", views.transferencia_formulario, name="transferencia_nueva"),
    path("ajustes/nuevo/", views.ajuste_formulario, name="ajuste_nuevo"),
    path("tipos/", views.tipos_lista, name="tipos"),
    path("tipos/nuevo/", views.tipo_formulario, name="tipo_nuevo"),
    path("tipos/<int:tipo_id>/editar/", views.tipo_formulario, name="tipo_editar"),
    path("<int:movimiento_id>/", views.movimiento_detalle, name="detalle"),
    path("<int:movimiento_id>/anular/", views.movimiento_anular, name="anular"),
]
