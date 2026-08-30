"""Registro de los modelos de configuración en el panel de administración."""

from django.contrib import admin

from apps.configuracion.models import (
    DefinicionCampo,
    Etiqueta,
    EtiquetaObjeto,
    FlujoAprobacion,
    MapeoImportacion,
    Parametro,
    PlantillaNotificacion,
    ValorCampo,
    VistaGuardada,
)


@admin.register(Parametro)
class AdminParametro(admin.ModelAdmin):
    """Administración de parámetros del sistema."""

    list_display = ["clave", "etiqueta", "valor", "tipo", "grupo", "editable"]
    list_filter = ["grupo", "tipo", "editable"]
    search_fields = ["clave", "etiqueta"]


@admin.register(DefinicionCampo)
class AdminDefinicionCampo(admin.ModelAdmin):
    """Administración de definiciones de campo personalizado."""

    list_display = ["entidad", "clave", "etiqueta", "tipo", "categoria", "requerido", "activo"]
    list_filter = ["entidad", "tipo", "requerido", "activo"]
    search_fields = ["clave", "etiqueta", "entidad"]
    ordering = ["entidad", "orden"]


@admin.register(ValorCampo)
class AdminValorCampo(admin.ModelAdmin):
    """Consulta de los valores guardados de los campos personalizados."""

    list_display = ["definicion", "objeto_id", "valor_texto", "valor_numero",
                    "valor_fecha", "valor_bool"]
    list_filter = ["definicion__entidad"]
    search_fields = ["objeto_id", "valor_texto"]


@admin.register(Etiqueta)
class AdminEtiqueta(admin.ModelAdmin):
    """Administración de etiquetas."""

    list_display = ["nombre", "color", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre"]


@admin.register(EtiquetaObjeto)
class AdminEtiquetaObjeto(admin.ModelAdmin):
    """Consulta de las etiquetas asignadas a objetos."""

    list_display = ["etiqueta", "entidad", "objeto_id"]
    list_filter = ["entidad"]


@admin.register(VistaGuardada)
class AdminVistaGuardada(admin.ModelAdmin):
    """Administración de vistas guardadas."""

    list_display = ["nombre", "entidad", "usuario", "compartida", "por_defecto"]
    list_filter = ["entidad", "compartida"]
    search_fields = ["nombre"]


@admin.register(FlujoAprobacion)
class AdminFlujoAprobacion(admin.ModelAdmin):
    """Administración de flujos de aprobación."""

    list_display = ["nombre", "entidad", "rol_aprobador", "orden", "activo"]
    list_filter = ["entidad", "activo"]


@admin.register(PlantillaNotificacion)
class AdminPlantillaNotificacion(admin.ModelAdmin):
    """Administración de plantillas de notificación."""

    list_display = ["clave", "asunto", "canal", "activa"]
    list_filter = ["canal", "activa"]
    search_fields = ["clave", "asunto"]


@admin.register(MapeoImportacion)
class AdminMapeoImportacion(admin.ModelAdmin):
    """Administración de mapeos de importación."""

    list_display = ["nombre", "entidad", "usuario", "creado_en"]
    list_filter = ["entidad"]
