"""Registro de los modelos de Alertas en el panel de administración."""

from django.contrib import admin

from apps.alertas.models import Alerta, ReglaAlerta


@admin.register(ReglaAlerta)
class AdminReglaAlerta(admin.ModelAdmin):
    """Administración de reglas de alerta."""

    list_display = ["nombre", "tipo", "dias_umbral", "activa"]
    list_filter = ["tipo", "activa"]
    search_fields = ["nombre"]
    filter_horizontal = ["almacenes", "categorias"]


@admin.register(Alerta)
class AdminAlerta(admin.ModelAdmin):
    """Administración de alertas. El estado se cambia desde la app, no aquí."""

    list_display = ["articulo", "almacen", "regla", "estado", "generada_en"]
    list_filter = ["estado", "regla"]
    search_fields = ["articulo__sku", "articulo__nombre", "mensaje"]
    readonly_fields = ["regla", "articulo", "almacen", "mensaje", "contexto", "generada_en"]
    list_select_related = ["articulo", "almacen", "regla"]
