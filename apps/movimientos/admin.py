"""Registro de los modelos de Movimientos en el panel de administración."""

from django.contrib import admin

from apps.movimientos.models import (
    ConsumoLote,
    Existencia,
    Lote,
    Movimiento,
    MovimientoLinea,
    TipoMovimiento,
)


@admin.register(TipoMovimiento)
class AdminTipoMovimiento(admin.ModelAdmin):
    """Administración de tipos de movimiento."""

    list_display = ["codigo", "nombre", "naturaleza", "exige_aprobacion", "activo"]
    list_filter = ["naturaleza", "activo", "exige_aprobacion"]
    search_fields = ["codigo", "nombre"]


class LineaInline(admin.TabularInline):
    """Muestra las líneas de un movimiento en su propia ficha."""

    model = MovimientoLinea
    extra = 0
    readonly_fields = ["articulo", "almacen", "signo", "cantidad", "costo_unitario",
                       "costo_total", "saldo_posterior"]
    can_delete = False


@admin.register(Movimiento)
class AdminMovimiento(admin.ModelAdmin):
    """Administración de movimientos. La confirmación y anulación viven en la app."""

    list_display = ["numero", "tipo", "estado", "fecha", "total_cantidad", "total_costo"]
    list_filter = ["estado", "tipo", "naturaleza"]
    search_fields = ["numero", "documento_numero", "ncf"]
    readonly_fields = ["naturaleza", "total_cantidad", "total_costo", "metodo_valoracion"]
    inlines = [LineaInline]


@admin.register(Lote)
class AdminLote(admin.ModelAdmin):
    """Administración de lotes, de solo lectura: los crea el servicio de movimientos."""

    list_display = ["codigo", "articulo", "almacen", "costo_unitario", "cantidad_disponible",
                    "cantidad_inicial", "recibido_en"]
    list_filter = ["almacen"]
    search_fields = ["codigo", "articulo__sku", "articulo__nombre"]
    readonly_fields = ["articulo", "almacen", "linea_origen", "costo_unitario",
                       "cantidad_inicial", "cantidad_disponible"]


@admin.register(Existencia)
class AdminExistencia(admin.ModelAdmin):
    """Administración de existencias."""

    list_display = ["articulo", "almacen", "cantidad", "valor", "stock_minimo"]
    list_filter = ["almacen"]
    search_fields = ["articulo__sku", "articulo__nombre"]
    readonly_fields = ["articulo", "almacen", "cantidad", "valor"]


admin.site.register(ConsumoLote)
