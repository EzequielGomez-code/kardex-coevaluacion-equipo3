"""Repositorios de Alertas. Única capa que consulta el ORM de estos modelos."""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.alertas.models import Alerta, EstadoAlerta, ReglaAlerta


class RepositorioReglas:
    """Acceso a datos de :class:`~apps.alertas.models.ReglaAlerta`."""

    @staticmethod
    def listar(solo_activas: bool = False) -> QuerySet[ReglaAlerta]:
        """Devuelve las reglas de alerta configuradas."""
        consulta = ReglaAlerta.objects.prefetch_related("almacenes", "categorias")
        if solo_activas:
            consulta = consulta.filter(activa=True)
        return consulta.order_by("nombre")

    @staticmethod
    def obtener(regla_id: int) -> ReglaAlerta | None:
        """Devuelve una regla por su identificador, o ``None``."""
        return ReglaAlerta.objects.filter(pk=regla_id).first()


class RepositorioAlertas:
    """Acceso a datos de :class:`~apps.alertas.models.Alerta`."""

    @staticmethod
    def listar(
        busqueda: str = "", estado: str = "", almacen_id: int | None = None,
    ) -> QuerySet[Alerta]:
        """Devuelve las alertas filtradas, con sus relaciones precargadas."""
        consulta = Alerta.objects.select_related("regla", "articulo", "almacen")
        if busqueda:
            consulta = consulta.filter(
                Q(articulo__sku__icontains=busqueda) | Q(articulo__nombre__icontains=busqueda)
                | Q(mensaje__icontains=busqueda)
            )
        if estado:
            consulta = consulta.filter(estado=estado)
        if almacen_id:
            consulta = consulta.filter(almacen_id=almacen_id)
        return consulta.order_by("-generada_en")

    @staticmethod
    def obtener(alerta_id: int) -> Alerta | None:
        """Devuelve una alerta por su identificador."""
        return Alerta.objects.select_related("regla", "articulo", "almacen").filter(
            pk=alerta_id
        ).first()

    @staticmethod
    def abierta_para(regla_id: int, articulo_id: int, almacen_id: int) -> Alerta | None:
        """Devuelve la alerta abierta (o en proceso) de esa regla, artículo y almacén, si existe."""
        return Alerta.objects.filter(
            regla_id=regla_id, articulo_id=articulo_id, almacen_id=almacen_id,
            estado__in=[EstadoAlerta.ABIERTA, EstadoAlerta.EN_PROCESO],
        ).first()

    @staticmethod
    def pares_abiertos_de_regla(regla_id: int) -> set[tuple[int, int]]:
        """Devuelve los pares (artículo, almacén) con alerta abierta o en proceso de esa regla."""
        return set(
            Alerta.objects.filter(
                regla_id=regla_id, estado__in=[EstadoAlerta.ABIERTA, EstadoAlerta.EN_PROCESO],
            ).values_list("articulo_id", "almacen_id")
        )

    @staticmethod
    def abiertas_de_reglas(reglas_ids: Iterable[int]) -> dict[tuple[int, int, int], Alerta]:
        """
        Devuelve, en **una sola consulta**, las alertas vivas de varias reglas,
        indexadas por ``(regla, artículo, almacén)``.

        Es lo que permite al evaluador decidir en memoria en vez de preguntar
        por cada par: con la base en otra región, una consulta por par hacía
        que «Evaluar ahora» superara el tiempo límite del servidor.
        """
        return {
            (alerta.regla_id, alerta.articulo_id, alerta.almacen_id): alerta
            for alerta in Alerta.objects.filter(
                regla_id__in=list(reglas_ids),
                estado__in=[EstadoAlerta.ABIERTA, EstadoAlerta.EN_PROCESO],
            )
        }

    @staticmethod
    def crear_muchas(alertas: list[Alerta]) -> None:
        """Inserta en bloque las alertas nuevas de una evaluación."""
        Alerta.objects.bulk_create(alertas)

    @staticmethod
    def actualizar_mensajes(alertas: list[Alerta]) -> None:
        """
        Guarda en bloque el mensaje y el contexto de alertas que ya existían.

        ``bulk_update`` no dispara ``auto_now``, así que ``actualizado_en`` va
        en la lista de campos y lo fija quien llama.
        """
        Alerta.objects.bulk_update(alertas, ["mensaje", "contexto", "actualizado_en"])

    @staticmethod
    def cerrar_muchas(alertas_ids: list[int], momento) -> int:
        """Marca como resueltas, en una sola consulta, las alertas indicadas."""
        return Alerta.objects.filter(pk__in=alertas_ids).update(
            estado=EstadoAlerta.RESUELTA, resuelta_en=momento, actualizado_en=momento,
        )

    @staticmethod
    def contar_abiertas() -> int:
        """Cuenta las alertas que siguen abiertas o en proceso."""
        return Alerta.objects.filter(
            estado__in=[EstadoAlerta.ABIERTA, EstadoAlerta.EN_PROCESO]
        ).count()
