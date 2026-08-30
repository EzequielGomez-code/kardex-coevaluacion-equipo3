"""
Repositorios de la app ``configuracion``.

Única capa que consulta el ORM de estos modelos. Sin reglas de negocio.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.configuracion.models import (
    DefinicionCampo,
    Etiqueta,
    EtiquetaObjeto,
    Parametro,
    ValorCampo,
    VistaGuardada,
)


class RepositorioParametros:
    """Acceso a datos de :class:`~apps.configuracion.models.Parametro`."""

    @staticmethod
    def listar(grupo: str = "", busqueda: str = "") -> QuerySet[Parametro]:
        """Devuelve los parámetros filtrados por grupo y texto."""
        consulta = Parametro.objects.all()
        if grupo:
            consulta = consulta.filter(grupo=grupo)
        if busqueda:
            consulta = consulta.filter(
                Q(clave__icontains=busqueda) | Q(etiqueta__icontains=busqueda)
            )
        return consulta.order_by("grupo", "orden", "clave")

    @staticmethod
    def obtener(clave: str) -> Parametro | None:
        """Devuelve un parámetro por su clave, o ``None``."""
        return Parametro.objects.filter(clave=clave).first()

    @staticmethod
    def grupos() -> list[str]:
        """Devuelve los grupos existentes, en orden alfabético."""
        return list(
            Parametro.objects.values_list("grupo", flat=True).distinct().order_by("grupo")
        )

    @staticmethod
    def todos() -> QuerySet[Parametro]:
        """Devuelve todos los parámetros."""
        return Parametro.objects.all().order_by("grupo", "orden", "clave")


class RepositorioDefinicionesCampo:
    """Acceso a datos de :class:`~apps.configuracion.models.DefinicionCampo`."""

    @staticmethod
    def listar(entidad: str = "", solo_activos: bool = False) -> QuerySet[DefinicionCampo]:
        """Devuelve las definiciones de campo, opcionalmente de una sola entidad."""
        consulta = DefinicionCampo.objects.all()
        if entidad:
            consulta = consulta.filter(entidad=entidad)
        if solo_activos:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("entidad", "orden", "clave")

    @staticmethod
    def para(entidad: str, categoria: str = "") -> QuerySet[DefinicionCampo]:
        """
        Devuelve los campos activos de una entidad.

        Incluye los campos generales (``categoria`` vacía) y, si se indica una
        categoría, también los propios de esa categoría.
        """
        filtro = Q(categoria="")
        if categoria:
            filtro |= Q(categoria=categoria)
        return (
            DefinicionCampo.objects.filter(entidad=entidad, activo=True)
            .filter(filtro)
            .order_by("orden", "clave")
        )

    @staticmethod
    def obtener(definicion_id: int) -> DefinicionCampo | None:
        """Devuelve una definición por su identificador, o ``None``."""
        return DefinicionCampo.objects.filter(pk=definicion_id).first()

    @staticmethod
    def existe_clave(entidad: str, categoria: str, clave: str,
                     excluir_id: int | None = None) -> bool:
        """Indica si ya hay un campo con esa clave en la entidad y categoría."""
        consulta = DefinicionCampo.objects.filter(
            entidad=entidad, categoria=categoria, clave=clave
        )
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def entidades() -> list[str]:
        """Devuelve las entidades que ya tienen campos definidos."""
        return list(
            DefinicionCampo.objects.values_list("entidad", flat=True)
            .distinct()
            .order_by("entidad")
        )

    @staticmethod
    def fijar_orden(pares: Iterable[tuple[int, int]]) -> None:
        """Guarda el nuevo orden a partir de pares ``(id, orden)``."""
        for definicion_id, orden in pares:
            DefinicionCampo.objects.filter(pk=definicion_id).update(orden=orden)


class RepositorioValoresCampo:
    """Acceso a datos de :class:`~apps.configuracion.models.ValorCampo`."""

    @staticmethod
    def de_objeto(entidad: str, objeto_id: str) -> QuerySet[ValorCampo]:
        """Devuelve los valores guardados para un objeto concreto."""
        return ValorCampo.objects.select_related("definicion").filter(
            definicion__entidad=entidad, objeto_id=str(objeto_id)
        )

    @staticmethod
    def guardar(definicion: DefinicionCampo, objeto_id: str, columnas: dict) -> ValorCampo:
        """Inserta o actualiza el valor de un campo para un objeto."""
        valor, _ = ValorCampo.objects.update_or_create(
            definicion=definicion, objeto_id=str(objeto_id), defaults=columnas
        )
        return valor

    @staticmethod
    def borrar_de_objeto(entidad: str, objeto_id: str) -> int:
        """Elimina todos los valores personalizados de un objeto que se borra."""
        borrados, _ = ValorCampo.objects.filter(
            definicion__entidad=entidad, objeto_id=str(objeto_id)
        ).delete()
        return borrados


class RepositorioEtiquetas:
    """Acceso a datos de etiquetas y sus asignaciones."""

    @staticmethod
    def listar(solo_activas: bool = False) -> QuerySet[Etiqueta]:
        """Devuelve las etiquetas del sistema."""
        consulta = Etiqueta.objects.all()
        if solo_activas:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("nombre")

    @staticmethod
    def de_objeto(entidad: str, objeto_id: str) -> QuerySet[EtiquetaObjeto]:
        """Devuelve las etiquetas pegadas a un objeto."""
        return EtiquetaObjeto.objects.select_related("etiqueta").filter(
            entidad=entidad, objeto_id=str(objeto_id)
        )


class RepositorioVistasGuardadas:
    """Acceso a datos de :class:`~apps.configuracion.models.VistaGuardada`."""

    @staticmethod
    def disponibles(usuario_id: int, entidad: str) -> QuerySet[VistaGuardada]:
        """Devuelve las vistas propias del usuario más las compartidas."""
        return VistaGuardada.objects.filter(entidad=entidad).filter(
            Q(usuario_id=usuario_id) | Q(compartida=True)
        ).order_by("nombre")
