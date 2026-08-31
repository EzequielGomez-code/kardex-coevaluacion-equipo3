"""Registro de los modelos del catálogo en el panel de administración."""

from django.contrib import admin

from apps.catalogo.models import (
    Articulo,
    Categoria,
    Cliente,
    Marca,
    Proveedor,
    ProveedorArticulo,
    UnidadMedida,
)


@admin.register(Categoria)
class AdminCategoria(admin.ModelAdmin):
    """Administración de categorías. El árbol se gestiona desde la interfaz propia."""

    list_display = ["ruta", "codigo", "nombre", "padre", "nivel", "activo"]
    list_filter = ["activo", "nivel"]
    search_fields = ["codigo", "nombre"]
    readonly_fields = ["ruta", "nivel", "secuencia_sku"]
    list_select_related = ["padre"]


@admin.register(Marca)
class AdminMarca(admin.ModelAdmin):
    """Administración de marcas."""

    list_display = ["nombre", "pais", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre"]


@admin.register(UnidadMedida)
class AdminUnidadMedida(admin.ModelAdmin):
    """Administración de unidades de medida."""

    list_display = ["codigo", "nombre", "permite_decimales", "activo"]
    list_filter = ["activo", "permite_decimales"]
    search_fields = ["codigo", "nombre"]


class LineaProveedorArticulo(admin.TabularInline):
    """Permite ver y editar los proveedores desde la ficha del artículo."""

    model = ProveedorArticulo
    extra = 0
    autocomplete_fields = ["proveedor"]


@admin.register(Articulo)
class AdminArticulo(admin.ModelAdmin):
    """Administración de artículos."""

    list_display = ["sku", "nombre", "categoria", "marca", "precio_venta", "activo"]
    list_filter = ["activo", "categoria", "marca", "maneja_lotes"]
    search_fields = ["sku", "nombre", "codigo_barras"]
    autocomplete_fields = ["categoria", "marca", "unidad"]
    list_select_related = ["categoria", "marca"]
    inlines = [LineaProveedorArticulo]


@admin.register(Proveedor)
class AdminProveedor(admin.ModelAdmin):
    """Administración de proveedores."""

    list_display = ["codigo", "razon_social", "rnc", "telefono", "activo"]
    list_filter = ["activo", "tipo_documento"]
    search_fields = ["codigo", "razon_social", "nombre_comercial", "rnc"]


@admin.register(Cliente)
class AdminCliente(admin.ModelAdmin):
    """Administración de clientes."""

    list_display = ["codigo", "razon_social", "rnc", "telefono", "activo"]
    list_filter = ["activo", "tipo_documento"]
    search_fields = ["codigo", "razon_social", "nombre_comercial", "rnc"]
