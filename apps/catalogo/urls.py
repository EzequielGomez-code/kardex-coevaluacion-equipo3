"""Rutas de la app ``catalogo``."""

from django.urls import path

from apps.catalogo import views

app_name = "catalogo"

urlpatterns = [
    # Categorías
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.categoria_formulario, name="categoria_nueva"),
    path(
        "categorias/<int:categoria_id>/editar/",
        views.categoria_formulario,
        name="categoria_editar",
    ),
    path(
        "categorias/<int:categoria_id>/eliminar/",
        views.categoria_eliminar,
        name="categoria_eliminar",
    ),
    path("categorias/reordenar/", views.categorias_reordenar, name="categorias_reordenar"),
    path("categorias/mover/", views.categorias_mover, name="categorias_mover"),
    # Marcas
    path("marcas/", views.marcas, name="marcas"),
    path("marcas/nueva/", views.marca_formulario, name="marca_nueva"),
    path("marcas/<int:marca_id>/editar/", views.marca_formulario, name="marca_editar"),
    # Unidades de medida
    path("unidades/", views.unidades, name="unidades"),
    path("unidades/nueva/", views.unidad_formulario, name="unidad_nueva"),
    path("unidades/<int:unidad_id>/editar/", views.unidad_formulario, name="unidad_editar"),
    # Artículos
    path("articulos/", views.articulos, name="articulos"),
    path("articulos/nuevo/", views.articulo_formulario, name="articulo_nuevo"),
    path("articulos/<int:articulo_id>/", views.articulo_detalle, name="articulo_detalle"),
    path(
        "articulos/<int:articulo_id>/editar/", views.articulo_formulario, name="articulo_editar"
    ),
    path(
        "articulos/<int:articulo_id>/eliminar/", views.articulo_eliminar, name="articulo_eliminar"
    ),
    path("articulos/campos/", views.articulo_campos_de_categoria, name="articulo_campos"),
    # Proveedores
    path("proveedores/", views.proveedores, name="proveedores"),
    path("proveedores/nuevo/", views.proveedor_formulario, name="proveedor_nuevo"),
    path(
        "proveedores/<int:proveedor_id>/editar/",
        views.proveedor_formulario,
        name="proveedor_editar",
    ),
    path(
        "proveedores/<int:proveedor_id>/estado/",
        views.proveedor_alternar_estado,
        name="proveedor_alternar",
    ),
    # Clientes
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_formulario, name="cliente_nuevo"),
    path("clientes/<int:cliente_id>/editar/", views.cliente_formulario, name="cliente_editar"),
    path(
        "clientes/<int:cliente_id>/estado/", views.cliente_alternar_estado, name="cliente_alternar"
    ),
    # Precios de proveedor por artículo
    path(
        "articulos/<int:articulo_id>/proveedores/nuevo/",
        views.precio_formulario,
        name="precio_nuevo",
    ),
    path("precios/<int:relacion_id>/editar/", views.precio_formulario, name="precio_editar"),
    path("precios/<int:relacion_id>/eliminar/", views.precio_eliminar, name="precio_eliminar"),
]
