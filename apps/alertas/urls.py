"""Rutas de la app ``alertas``."""

from django.urls import path

from apps.alertas import views, vistas_reportes

app_name = "alertas"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("evaluar/", views.evaluar_ahora, name="evaluar_ahora"),
    path("reglas/", views.reglas, name="reglas"),
    path("reglas/nueva/", views.regla_formulario, name="regla_nueva"),
    path("reglas/<int:regla_id>/editar/", views.regla_formulario, name="regla_editar"),
    path("reportes/", vistas_reportes.indice, name="reportes_indice"),
    path("reportes/existencias.pdf", vistas_reportes.existencias_pdf, name="reporte_existencias_pdf"),
    path("reportes/existencias.xlsx", vistas_reportes.existencias_excel, name="reporte_existencias_excel"),
    path("reportes/valorizacion.pdf", vistas_reportes.valorizacion_pdf, name="reporte_valorizacion_pdf"),
    path("reportes/valorizacion.xlsx", vistas_reportes.valorizacion_excel, name="reporte_valorizacion_excel"),
    path("reportes/movimientos.pdf", vistas_reportes.movimientos_pdf, name="reporte_movimientos_pdf"),
    path("reportes/movimientos.xlsx", vistas_reportes.movimientos_excel, name="reporte_movimientos_excel"),
    path("reportes/kardex.pdf", vistas_reportes.kardex_pdf, name="reporte_kardex_pdf"),
    path("reportes/kardex.xlsx", vistas_reportes.kardex_excel, name="reporte_kardex_excel"),
    path("<int:alerta_id>/estado/", views.alerta_cambiar_estado, name="alerta_estado"),
]
