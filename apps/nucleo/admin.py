"""
Registro de los modelos del núcleo en el panel de administración de Django.

El panel es una herramienta de respaldo para el administrador de TI; la
operación diaria ocurre en la interfaz propia de Kardex. La auditoría se
registra en modo solo lectura para no romper su inmutabilidad (Seguridad #8).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.nucleo.models import Almacen, Permiso, RegistroAuditoria, Rol, RolPermiso, Usuario


class LineaRolPermiso(admin.TabularInline):
    """Permite asignar permisos desde la ficha del rol."""

    model = RolPermiso
    extra = 0
    autocomplete_fields = ["permiso"]


@admin.register(Rol)
class AdminRol(admin.ModelAdmin):
    """Administración de roles."""

    list_display = ["nombre", "descripcion", "es_sistema"]
    list_filter = ["es_sistema"]
    search_fields = ["nombre", "descripcion"]
    inlines = [LineaRolPermiso]


@admin.register(Permiso)
class AdminPermiso(admin.ModelAdmin):
    """Administración de permisos."""

    list_display = ["clave", "modulo", "descripcion"]
    list_filter = ["modulo"]
    search_fields = ["clave", "descripcion"]


@admin.register(Usuario)
class AdminUsuario(UserAdmin):
    """Administración de usuarios, con los campos propios de Kardex."""

    list_display = ["username", "nombre_completo", "rol", "activo", "is_superuser"]
    list_filter = ["activo", "rol", "is_superuser"]
    search_fields = ["username", "nombre_completo", "email"]
    fieldsets = UserAdmin.fieldsets + (
        ("Datos de Kardex", {"fields": ("rol", "nombre_completo", "telefono", "activo")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos de Kardex", {"fields": ("rol", "nombre_completo", "telefono", "activo")}),
    )


@admin.register(Almacen)
class AdminAlmacen(admin.ModelAdmin):
    """Administración de almacenes."""

    list_display = ["codigo", "nombre", "encargado", "activo"]
    list_filter = ["activo"]
    search_fields = ["codigo", "nombre", "direccion"]


@admin.register(RegistroAuditoria)
class AdminRegistroAuditoria(admin.ModelAdmin):
    """Auditoría en modo solo lectura: no se puede agregar, editar ni borrar."""

    list_display = ["creado_en", "usuario", "accion", "entidad", "entidad_id", "ip"]
    list_filter = ["accion", "entidad"]
    search_fields = ["entidad", "entidad_id"]
    date_hierarchy = "creado_en"

    def has_add_permission(self, request) -> bool:
        """La auditoría solo la escribe el sistema."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Los registros de auditoría son inmutables."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Los registros de auditoría no se eliminan."""
        return False
