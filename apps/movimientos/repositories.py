"""
Repositorios de Movimientos.

Única capa que consulta el ORM de estos modelos. Sin reglas de negocio: cada
método recibe criterios ya resueltos y devuelve objetos o conjuntos de
consulta.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField, F, Q, QuerySet, Sum
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.movimientos.models import (
    ConsumoLote,
    EstadoMovimiento,
    Existencia,
    Lote,
    Movimiento,
    MovimientoLinea,
    TipoMovimiento,
)


class RepositorioTiposMovimiento:
    """Acceso a datos de :class:`~apps.movimientos.models.TipoMovimiento`."""

    @staticmethod
    def listar(solo_activos: bool = False) -> QuerySet[TipoMovimiento]:
        """Devuelve los tipos de movimiento configurados."""
        consulta = TipoMovimiento.objects.select_related("tipo_contrapartida")
        if solo_activos:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("orden", "codigo")

    @staticmethod
    def obtener(tipo_id: int) -> TipoMovimiento | None:
        """Devuelve un tipo de movimiento por su identificador, o ``None``."""
        return TipoMovimiento.objects.filter(pk=tipo_id).first()

    @staticmethod
    def existe_codigo(codigo: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro tipo de movimiento con ese código."""
        consulta = TipoMovimiento.objects.filter(codigo__iexact=codigo)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()


class RepositorioMovimientos:
    """Acceso a datos de :class:`~apps.movimientos.models.Movimiento`."""

    @staticmethod
    def listar(
        busqueda: str = "", tipo_id: int | None = None, almacen_id: int | None = None,
        estado: str = "", desde=None, hasta=None,
    ) -> QuerySet[Movimiento]:
        """Devuelve los movimientos filtrados, con sus relaciones precargadas."""
        consulta = Movimiento.objects.select_related(
            "tipo", "almacen_origen", "almacen_destino", "usuario", "proveedor", "cliente"
        )
        if busqueda:
            consulta = consulta.filter(
                Q(numero__icontains=busqueda)
                | Q(documento_numero__icontains=busqueda)
                | Q(ncf__icontains=busqueda)
            )
        if tipo_id:
            consulta = consulta.filter(tipo_id=tipo_id)
        if almacen_id:
            consulta = consulta.filter(
                Q(almacen_origen_id=almacen_id) | Q(almacen_destino_id=almacen_id)
            )
        if estado:
            consulta = consulta.filter(estado=estado)
        if desde:
            consulta = consulta.filter(fecha__gte=desde)
        if hasta:
            consulta = consulta.filter(fecha__lte=hasta)
        return consulta.order_by("-fecha", "-id")

    @staticmethod
    def obtener(movimiento_id: int) -> Movimiento | None:
        """Devuelve un movimiento con sus líneas y lotes creados precargados."""
        return (
            Movimiento.objects.select_related(
                "tipo", "almacen_origen", "almacen_destino", "usuario",
                "aprobado_por", "proveedor", "cliente", "anula",
            )
            .prefetch_related("lineas__articulo", "lineas__almacen", "anulaciones")
            .filter(pk=movimiento_id)
            .first()
        )

    @staticmethod
    def pendientes_de_aprobacion() -> QuerySet[Movimiento]:
        """Devuelve los movimientos que esperan aprobación."""
        return (
            Movimiento.objects.select_related("tipo", "usuario")
            .filter(estado=EstadoMovimiento.PENDIENTE)
            .order_by("fecha")
        )

    @staticmethod
    def existe_numero(numero: str) -> bool:
        """Indica si ya existe un movimiento con ese número."""
        return Movimiento.objects.filter(numero=numero).exists()

    @staticmethod
    def existe_ncf(proveedor_id: int, ncf: str, excluir_id: int | None = None) -> bool:
        """Indica si ese proveedor ya tiene registrado ese comprobante fiscal."""
        if not ncf:
            return False
        consulta = Movimiento.objects.filter(proveedor_id=proveedor_id, ncf=ncf)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def siguiente_secuencia(tipo: TipoMovimiento) -> int:
        """Incrementa y devuelve la secuencia numérica del tipo, bajo bloqueo."""
        tipo_bloqueado = TipoMovimiento.objects.select_for_update().get(pk=tipo.pk)
        tipo_bloqueado.secuencia_actual += 1
        tipo_bloqueado.save(update_fields=["secuencia_actual"])
        return tipo_bloqueado.secuencia_actual


class RepositorioLotes:
    """Acceso a datos de :class:`~apps.movimientos.models.Lote`."""

    @staticmethod
    def disponibles_bloqueados(articulo_id: int, almacen_id: int, orden: str) -> QuerySet[Lote]:
        """
        Devuelve, bajo ``select_for_update``, los lotes con saldo de un
        artículo en un almacén, en el orden de consumo indicado.
        """
        return (
            Lote.objects.select_for_update()
            .filter(articulo_id=articulo_id, almacen_id=almacen_id, cantidad_disponible__gt=0)
            .order_by(orden, "id")
        )

    @staticmethod
    def de_articulo(articulo_id: int, almacen_id: int | None = None) -> QuerySet[Lote]:
        """Devuelve los lotes de un artículo, opcionalmente filtrados por almacén."""
        consulta = Lote.objects.select_related("almacen").filter(articulo_id=articulo_id)
        if almacen_id:
            consulta = consulta.filter(almacen_id=almacen_id)
        return consulta.order_by("recibido_en", "id")

    @staticmethod
    def por_vencer(dias: int) -> QuerySet[Lote]:
        """Devuelve los lotes con saldo que vencen dentro de ``dias`` días."""
        limite = timezone.localdate() + timezone.timedelta(days=dias)
        return (
            Lote.objects.select_related("articulo", "almacen")
            .filter(cantidad_disponible__gt=0, fecha_vencimiento__isnull=False,
                   fecha_vencimiento__lte=limite)
            .order_by("fecha_vencimiento")
        )


class RepositorioExistencias:
    """Acceso a datos de :class:`~apps.movimientos.models.Existencia`."""

    @staticmethod
    def listar(
        busqueda: str = "", almacen_id: int | None = None, solo_bajo_minimo: bool = False,
    ) -> QuerySet[Existencia]:
        """Devuelve las existencias filtradas, con artículo y almacén precargados."""
        consulta = Existencia.objects.select_related("articulo", "almacen", "articulo__unidad")
        if busqueda:
            consulta = consulta.filter(
                Q(articulo__sku__icontains=busqueda) | Q(articulo__nombre__icontains=busqueda)
            )
        if almacen_id:
            consulta = consulta.filter(almacen_id=almacen_id)
        if solo_bajo_minimo:
            consulta = consulta.filter(cantidad__lt=F("stock_minimo"))
        return consulta.order_by("articulo__nombre", "almacen__codigo")

    @staticmethod
    def bloqueada(articulo_id: int, almacen_id: int) -> Existencia:
        """
        Devuelve, creándola si hace falta, la fila de existencia bajo bloqueo.

        Cada artículo tiene una fila de existencia por almacén desde el
        primer movimiento que lo toca; la regla de no-negativo necesita una
        fila real que bloquear, no un agregado calculado al vuelo. Al
        crearla, el mínimo arranca en el valor por defecto del artículo —
        de ahí en más se edita por almacén, no vuelve a copiarse.
        """
        existencia, creada = Existencia.objects.get_or_create(
            articulo_id=articulo_id, almacen_id=almacen_id
        )
        if creada:
            minimo_por_defecto = Articulo.objects.filter(pk=articulo_id).values_list(
                "stock_minimo_defecto", flat=True
            ).first()
            if minimo_por_defecto:
                existencia.stock_minimo = minimo_por_defecto
                existencia.save(update_fields=["stock_minimo"])
        return Existencia.objects.select_for_update().get(pk=existencia.pk)

    @staticmethod
    def de_articulo(articulo_id: int) -> QuerySet[Existencia]:
        """Devuelve las existencias de un artículo en todos los almacenes."""
        return (
            Existencia.objects.select_related("almacen")
            .filter(articulo_id=articulo_id)
            .order_by("almacen__codigo")
        )

    @staticmethod
    def total_valor() -> Decimal:
        """Devuelve el valor total del inventario, sumado sobre todas las existencias."""
        total = Existencia.objects.aggregate(total=Sum("valor"))["total"]
        return total if total is not None else Decimal("0")

    @staticmethod
    def valor_por_almacen() -> list[dict]:
        """Devuelve el valor de inventario agrupado por almacén, de mayor a menor."""
        return list(
            Existencia.objects.values("almacen__codigo", "almacen__nombre")
            .annotate(total=Sum("valor"))
            .order_by("-total")
        )


class RepositorioKardex:
    """Acceso a datos para el historial cronológico de un artículo."""

    @staticmethod
    def lineas_de(
        articulo_id: int, almacen_id: int | None = None
    ) -> QuerySet[MovimientoLinea]:
        """Devuelve las líneas de un artículo, en orden cronológico, sin N+1."""
        consulta = (
            MovimientoLinea.objects.select_related(
                "movimiento", "movimiento__tipo", "almacen"
            )
            .prefetch_related("consumos__lote")
            .filter(articulo_id=articulo_id)
        )
        if almacen_id:
            consulta = consulta.filter(almacen_id=almacen_id)
        return consulta.order_by("id")

    @staticmethod
    def saldo_antes_de(articulo_id: int, almacen_id: int, linea_id: int) -> Decimal:
        """
        Suma con signo de todas las líneas anteriores a ``linea_id``.

        Se usa para resolver el saldo corrido de una página del kardex sin
        traer todas las líneas anteriores: basta un ``aggregate`` sobre ellas.
        """
        total = MovimientoLinea.objects.filter(
            articulo_id=articulo_id, almacen_id=almacen_id, id__lt=linea_id
        ).aggregate(
            total=Sum(F("signo") * F("cantidad"), output_field=DecimalField(
                max_digits=18, decimal_places=4
            ))
        )["total"]
        return total if total is not None else Decimal("0")


class RepositorioConsumos:
    """Acceso a datos de :class:`~apps.movimientos.models.ConsumoLote`."""

    @staticmethod
    def de_linea(linea_id: int) -> QuerySet[ConsumoLote]:
        """Devuelve de qué lotes salió una línea de movimiento."""
        return ConsumoLote.objects.select_related("lote").filter(linea_id=linea_id).order_by("id")
