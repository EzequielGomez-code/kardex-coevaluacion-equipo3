"""Rutas de la app ``nucleo``."""

from django.urls import path

from apps.nucleo import views

app_name = "nucleo"

urlpatterns = [
    # Acceso
    path("acceso/", views.iniciar_sesion, name="iniciar_sesion"),
    path("salir/", views.cerrar_sesion, name="cerrar_sesion"),
    # Panel
    path("", views.panel, name="panel"),
    # Almacenes
    path("almacenes/", views.almacenes, name="almacenes"),
    path("almacenes/nuevo/", views.almacen_formulario, name="almacen_nuevo"),
    path("almacenes/<int:almacen_id>/editar/", views.almacen_formulario, name="almacen_editar"),
    path(
        "almacenes/<int:almacen_id>/eliminar/", views.almacen_eliminar, name="almacen_eliminar"
    ),
    # Usuarios
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_formulario, name="usuario_nuevo"),
    path("usuarios/<int:usuario_id>/editar/", views.usuario_formulario, name="usuario_editar"),
    path(
        "usuarios/<int:usuario_id>/estado/",
        views.usuario_alternar_estado,
        name="usuario_alternar",
    ),
    path(
        "usuarios/<int:usuario_id>/eliminar/", views.usuario_eliminar, name="usuario_eliminar"
    ),
    # Roles
    path("roles/", views.roles, name="roles"),
    path("roles/nuevo/", views.rol_formulario, name="rol_nuevo"),
    path("roles/<int:rol_id>/editar/", views.rol_formulario, name="rol_editar"),
    path("roles/<int:rol_id>/eliminar/", views.rol_eliminar, name="rol_eliminar"),
    # Auditoría
    path("auditoria/", views.auditoria, name="auditoria"),
    # Perfil y buscador
    path("perfil/", views.perfil, name="perfil"),
    path("buscar/", views.buscador, name="buscador"),
    # Reinicio de datos de demostración: sin entrada en el menú a propósito.
    path("sistema/reiniciar-demo/", views.reiniciar_demo, name="reiniciar_demo"),
]
