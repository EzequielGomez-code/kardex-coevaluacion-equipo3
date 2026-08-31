"""
Repositorios del núcleo.

Única capa autorizada a tocar el ORM para los modelos de esta app. Un
repositorio no toma decisiones de negocio: recibe criterios ya resueltos y
devuelve objetos o conjuntos de consulta. Regla de capas del punto 3 del brief.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Count, Q, QuerySet

from apps.nucleo.models import (
    NOMBRE_ROL_OCULTO,
    Almacen,
    Permiso,
    RegistroAuditoria,
    Rol,
    RolPermiso,
    Usuario,
)


class RepositorioRoles:
    """Acceso a datos de :class:`~apps.nucleo.models.Rol`."""

    @staticmethod
    def listar(busqueda: str = "") -> QuerySet[Rol]:
        """
        Devuelve los roles, opcionalmente filtrados por nombre o descripción.

        Excluye siempre el rol oculto: no aparece en la pantalla de roles.
        """
        consulta = (
            Rol.objects.exclude(nombre=NOMBRE_ROL_OCULTO)
            .annotate(total_usuarios=Count("usuarios", distinct=True))
        )
        if busqueda:
            consulta = consulta.filter(
                Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda)
            )
        return consulta.order_by("nombre")

    @staticmethod
    def obtener(rol_id: int) -> Rol | None:
        """Devuelve un rol por su identificador, o ``None`` si no existe."""
        return Rol.objects.filter(pk=rol_id).first()

    @staticmethod
    def obtener_por_nombre(nombre: str) -> Rol | None:
        """Devuelve un rol por su nombre exacto, o ``None``."""
        return Rol.objects.filter(nombre=nombre).first()

    @staticmethod
    def crear(nombre: str, descripcion: str = "", es_sistema: bool = False) -> Rol:
        """Inserta un rol nuevo."""
        return Rol.objects.create(
            nombre=nombre, descripcion=descripcion, es_sistema=es_sistema
        )

    @staticmethod
    def reemplazar_permisos(rol: Rol, claves: Iterable[str]) -> None:
        """Deja el rol exactamente con los permisos indicados por sus claves."""
        permisos = list(Permiso.objects.filter(clave__in=list(claves)))
        RolPermiso.objects.filter(rol=rol).delete()
        RolPermiso.objects.bulk_create(
            [RolPermiso(rol=rol, permiso=permiso) for permiso in permisos]
        )

    @staticmethod
    def claves_de(rol: Rol) -> set[str]:
        """Devuelve las claves de permiso asignadas al rol."""
        return set(
            Permiso.objects.filter(roles__id=rol.pk).values_list("clave", flat=True)
        )

    @staticmethod
    def cuenta_de_usuarios(rol: Rol) -> int:
        """Cuenta los usuarios que tienen asignado el rol."""
        return Usuario.objects.filter(rol=rol).count()


class RepositorioPermisos:
    """Acceso a datos de :class:`~apps.nucleo.models.Permiso`."""

    @staticmethod
    def listar() -> QuerySet[Permiso]:
        """Devuelve todos los permisos ordenados por módulo."""
        return Permiso.objects.all().order_by("modulo", "clave")

    @staticmethod
    def agrupados_por_modulo() -> dict[str, list[Permiso]]:
        """Devuelve los permisos agrupados por módulo, para pintar la pantalla de roles."""
        grupos: dict[str, list[Permiso]] = {}
        for permiso in RepositorioPermisos.listar():
            grupos.setdefault(permiso.modulo, []).append(permiso)
        return grupos


class RepositorioUsuarios:
    """Acceso a datos de :class:`~apps.nucleo.models.Usuario`."""

    @staticmethod
    def listar(busqueda: str = "", rol_id: int | None = None,
               estado: str = "") -> QuerySet[Usuario]:
        """Devuelve los usuarios filtrados por texto, rol y estado."""
        consulta = Usuario.objects.select_related("rol")
        if busqueda:
            consulta = consulta.filter(
                Q(username__icontains=busqueda)
                | Q(nombre_completo__icontains=busqueda)
                | Q(email__icontains=busqueda)
            )
        if rol_id:
            consulta = consulta.filter(rol_id=rol_id)
        if estado == "activo":
            consulta = consulta.filter(activo=True)
        elif estado == "inactivo":
            consulta = consulta.filter(activo=False)
        return consulta.order_by("username")

    @staticmethod
    def obtener(usuario_id: int) -> Usuario | None:
        """Devuelve un usuario por su identificador, o ``None``."""
        return Usuario.objects.select_related("rol").filter(pk=usuario_id).first()

    @staticmethod
    def existe_nombre(username: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro usuario con ese nombre de acceso."""
        consulta = Usuario.objects.filter(username__iexact=username)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()


class RepositorioAlmacenes:
    """Acceso a datos de :class:`~apps.nucleo.models.Almacen`."""

    @staticmethod
    def listar(busqueda: str = "", estado: str = "") -> QuerySet[Almacen]:
        """Devuelve los almacenes filtrados por texto y estado."""
        consulta = Almacen.objects.select_related("encargado")
        if busqueda:
            consulta = consulta.filter(
                Q(codigo__icontains=busqueda)
                | Q(nombre__icontains=busqueda)
                | Q(direccion__icontains=busqueda)
            )
        if estado == "activo":
            consulta = consulta.filter(activo=True)
        elif estado == "inactivo":
            consulta = consulta.filter(activo=False)
        return consulta.order_by("codigo")

    @staticmethod
    def activos() -> QuerySet[Almacen]:
        """Devuelve solo los almacenes en operación."""
        return Almacen.objects.filter(activo=True).order_by("codigo")

    @staticmethod
    def obtener(almacen_id: int) -> Almacen | None:
        """Devuelve un almacén por su identificador, o ``None``."""
        return Almacen.objects.select_related("encargado").filter(pk=almacen_id).first()

    @staticmethod
    def existe_codigo(codigo: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro almacén con ese código."""
        consulta = Almacen.objects.filter(codigo__iexact=codigo)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def tiene_movimientos(almacen: Almacen) -> bool:
        """
        Indica si el almacén ya tiene movimientos de entrada o salida.

        Usa las relaciones inversas que ``Movimiento`` ya declara sobre
        ``Almacen`` (``movimientos_salida`` / ``movimientos_entrada``), sin
        importar el modelo de la app ``movimientos`` aquí — igual que
        ``RepositorioArticulos.tiene_movimientos`` en el catálogo.
        """
        return almacen.movimientos_salida.exists() or almacen.movimientos_entrada.exists()


class RepositorioAuditoria:
    """
    Acceso a datos de :class:`~apps.nucleo.models.RegistroAuditoria`.

    Solo expone lectura y alta. No hay método de actualización ni de borrado a
    propósito: la inmutabilidad se defiende en el modelo y también aquí.
    """

    @staticmethod
    def registrar(**datos) -> RegistroAuditoria:
        """Inserta un registro de auditoría."""
        return RegistroAuditoria.objects.create(**datos)

    @staticmethod
    def listar(entidad: str = "", accion: str = "", usuario_id: int | None = None,
               busqueda: str = "") -> QuerySet[RegistroAuditoria]:
        """Devuelve los registros filtrados por entidad, acción, usuario y texto."""
        consulta = RegistroAuditoria.objects.select_related("usuario")
        if entidad:
            consulta = consulta.filter(entidad=entidad)
        if accion:
            consulta = consulta.filter(accion=accion)
        if usuario_id:
            consulta = consulta.filter(usuario_id=usuario_id)
        if busqueda:
            consulta = consulta.filter(
                Q(entidad__icontains=busqueda) | Q(entidad_id__icontains=busqueda)
            )
        return consulta.order_by("-creado_en", "-id")

    @staticmethod
    def entidades_registradas() -> list[str]:
        """Devuelve las entidades que ya aparecen en la auditoría, para el filtro."""
        return list(
            RegistroAuditoria.objects.values_list("entidad", flat=True)
            .distinct()
            .order_by("entidad")
        )
