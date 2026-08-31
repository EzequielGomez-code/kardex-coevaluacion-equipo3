"""
Servicios de Alertas.

``ServicioEvaluador`` es el corazón del módulo: compara el estado real del
inventario contra cada regla activa y abre o cierra alertas según lo que
encuentra. Nunca duplica una alerta abierta — eso lo garantiza la restricción
única parcial del modelo — así que el evaluador puede correr todas las veces
que haga falta sin generar ruido.

Se llama desde tres lugares, tal como pide el brief para un plan gratuito sin
tareas programadas: al confirmar un movimiento (solo sobre los pares que
tocó), con el botón «Evaluar ahora», y con el comando ``evaluar_alertas`` para
un ping externo.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.alertas.models import Alerta, EstadoAlerta, ReglaAlerta, TipoRegla
from apps.alertas.repositories import RepositorioAlertas, RepositorioReglas
from apps.catalogo.models import Articulo
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria


class ServicioReglas:
    """Alta y edición de reglas de alerta."""

    @staticmethod
    def listar(solo_activas: bool = False):
        """Devuelve las reglas configuradas."""
        return RepositorioReglas.listar(solo_activas=solo_activas)

    @staticmethod
    def obtener(regla_id: int) -> ReglaAlerta | None:
        """Devuelve una regla por su identificador."""
        return RepositorioReglas.obtener(regla_id)

    @staticmethod
    @transaction.atomic
    def crear(**datos) -> ReglaAlerta:
        """
        Crea una regla de alerta.

        :raises ValidationError: si el tipo exige días de margen y no se dio.
        """
        tipo = datos["tipo"]
        dias_umbral = datos.get("dias_umbral")
        tipos_con_dias = (TipoRegla.SIN_MOVIMIENTO, TipoRegla.VENCIMIENTO_PROXIMO)
        if tipo in tipos_con_dias and not dias_umbral:
            raise ValidationError({"dias_umbral": "Este tipo de regla necesita días de margen."})

        regla = ReglaAlerta.objects.create(
            nombre=datos["nombre"].strip(), tipo=tipo,
            dias_umbral=dias_umbral if tipo in tipos_con_dias else None,
            activa=datos.get("activa", True),
        )
        regla.almacenes.set(datos.get("almacenes") or [])
        regla.categorias.set(datos.get("categorias") or [])
        ServicioAuditoria.registrar(
            entidad="ReglaAlerta", entidad_id=regla.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"nombre": regla.nombre, "tipo": regla.tipo},
        )
        return regla

    @staticmethod
    @transaction.atomic
    def actualizar(regla: ReglaAlerta, **datos) -> ReglaAlerta:
        """Actualiza una regla de alerta. El tipo no se toca aquí."""
        regla.nombre = datos.get("nombre", regla.nombre).strip()
        if regla.tipo in (TipoRegla.SIN_MOVIMIENTO, TipoRegla.VENCIMIENTO_PROXIMO):
            dias_umbral = datos.get("dias_umbral")
            if not dias_umbral:
                raise ValidationError({"dias_umbral": "Este tipo de regla necesita días de margen."})
            regla.dias_umbral = dias_umbral
        regla.activa = datos.get("activa", regla.activa)
        regla.save()
        if "almacenes" in datos:
            regla.almacenes.set(datos["almacenes"] or [])
        if "categorias" in datos:
            regla.categorias.set(datos["categorias"] or [])
        ServicioAuditoria.registrar(
            entidad="ReglaAlerta", entidad_id=regla.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"nombre": regla.nombre},
        )
        return regla


class ServicioAlertas:
    """Consulta y resolución de alertas ya generadas."""

    @staticmethod
    def listar(**filtros):
        """Devuelve las alertas filtradas."""
        return RepositorioAlertas.listar(**filtros)

    @staticmethod
    def obtener(alerta_id: int) -> Alerta | None:
        """Devuelve una alerta por su identificador."""
        return RepositorioAlertas.obtener(alerta_id)

    @staticmethod
    def contar_abiertas() -> int:
        """Cuenta las alertas abiertas o en proceso, para el indicador del menú."""
        return RepositorioAlertas.contar_abiertas()

    @staticmethod
    @transaction.atomic
    def cambiar_estado(alerta: Alerta, estado: str, usuario) -> Alerta:
        """
        Cambia el estado de una alerta (en proceso, resuelta, ignorada).

        :raises ValidationError: si el estado no es uno de los válidos.
        """
        if estado not in EstadoAlerta.values:
            raise ValidationError("Estado de alerta inválido.")
        alerta.estado = estado
        if estado in (EstadoAlerta.RESUELTA, EstadoAlerta.IGNORADA):
            alerta.resuelta_en = timezone.now()
            alerta.resuelta_por = usuario
        alerta.save()
        ServicioAuditoria.registrar(
            entidad="Alerta", entidad_id=alerta.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "cambiar_estado", "estado": estado},
        )
        return alerta


def _regla_aplica(regla: ReglaAlerta, articulo: Articulo, almacen_id: int,
                  almacenes_por_regla: dict, categorias_por_regla: dict) -> bool:
    """Indica si una regla vigila este artículo en este almacén."""
    almacenes_ids = almacenes_por_regla[regla.pk]
    if almacenes_ids and almacen_id not in almacenes_ids:
        return False
    categorias_ids = categorias_por_regla[regla.pk]
    if categorias_ids and articulo.categoria_id not in categorias_ids:
        return False
    return True


def _abrir_o_actualizar(regla_id: int, articulo_id: int, almacen_id: int, mensaje: str,
                        contexto: dict) -> None:
    """Abre una alerta nueva, o actualiza el mensaje si ya había una abierta."""
    existente = RepositorioAlertas.abierta_para(regla_id, articulo_id, almacen_id)
    if existente:
        if existente.mensaje != mensaje or existente.contexto != contexto:
            existente.mensaje = mensaje
            existente.contexto = contexto
            existente.save(update_fields=["mensaje", "contexto", "actualizado_en"])
        return
    Alerta.objects.create(
        regla_id=regla_id, articulo_id=articulo_id, almacen_id=almacen_id,
        mensaje=mensaje, contexto=contexto,
    )


def _cerrar_si_ya_no_aplica(regla_id: int, articulo_id: int, almacen_id: int) -> None:
    """Resuelve automáticamente una alerta abierta cuya condición ya no se cumple."""
    existente = RepositorioAlertas.abierta_para(regla_id, articulo_id, almacen_id)
    if existente:
        existente.estado = EstadoAlerta.RESUELTA
        existente.resuelta_en = timezone.now()
        existente.save(update_fields=["estado", "resuelta_en", "actualizado_en"])


def _evaluar_stock(regla: ReglaAlerta, existencia) -> None:
    """Evalúa las reglas de existencia (bajo mínimo o en cero) sobre una fila de existencia."""
    articulo_id, almacen_id = existencia.articulo_id, existencia.almacen_id
    if regla.tipo == TipoRegla.STOCK_CERO:
        if existencia.cantidad <= 0:
            _abrir_o_actualizar(
                regla.pk, articulo_id, almacen_id,
                f"{existencia.articulo.sku} está en cero en {existencia.almacen.codigo}.",
                {"cantidad": str(existencia.cantidad)},
            )
        else:
            _cerrar_si_ya_no_aplica(regla.pk, articulo_id, almacen_id)
    elif regla.tipo == TipoRegla.STOCK_BAJO:
        if 0 < existencia.cantidad < existencia.stock_minimo:
            _abrir_o_actualizar(
                regla.pk, articulo_id, almacen_id,
                f"{existencia.articulo.sku} tiene {existencia.cantidad} unidades en "
                f"{existencia.almacen.codigo}, por debajo del mínimo ({existencia.stock_minimo}).",
                {"cantidad": str(existencia.cantidad), "minimo": str(existencia.stock_minimo)},
            )
        else:
            _cerrar_si_ya_no_aplica(regla.pk, articulo_id, almacen_id)


def _evaluar_sin_movimiento(regla: ReglaAlerta, existencia) -> None:
    """Evalúa si un artículo lleva demasiado tiempo sin movimiento."""
    limite = timezone.now() - timedelta(days=regla.dias_umbral)
    sin_movimiento = (
        existencia.ultimo_movimiento_en is None or existencia.ultimo_movimiento_en < limite
    )
    if sin_movimiento and existencia.cantidad > 0:
        dias = (
            (timezone.now() - existencia.ultimo_movimiento_en).days
            if existencia.ultimo_movimiento_en else None
        )
        _abrir_o_actualizar(
            regla.pk, existencia.articulo_id, existencia.almacen_id,
            f"{existencia.articulo.sku} no tiene movimientos en {existencia.almacen.codigo} "
            f"desde hace {dias if dias is not None else 'siempre'} días.",
            {"dias_sin_movimiento": dias},
        )
    else:
        _cerrar_si_ya_no_aplica(regla.pk, existencia.articulo_id, existencia.almacen_id)


def _evaluar_vencimiento(regla: ReglaAlerta) -> None:
    """Evalúa los lotes con saldo que vencen dentro del margen de la regla."""
    from apps.movimientos.repositories import RepositorioLotes  # pylint: disable=import-outside-toplevel

    for lote in RepositorioLotes.por_vencer(regla.dias_umbral):
        _abrir_o_actualizar(
            regla.pk, lote.articulo_id, lote.almacen_id,
            f"El lote {lote.codigo} de {lote.articulo.sku} vence el "
            f"{lote.fecha_vencimiento:%d/%m/%Y}.",
            {"lote": lote.codigo, "vencimiento": lote.fecha_vencimiento.isoformat()},
        )


class ServicioEvaluador:
    """Compara el inventario contra las reglas activas y abre o cierra alertas."""

    @staticmethod
    @transaction.atomic
    def evaluar_pares(pares: Iterable[tuple[int, int]]) -> int:
        """
        Evalúa solo los pares (artículo, almacén) indicados — se llama justo
        después de confirmar un movimiento, para no recorrer todo el
        inventario en cada operación.

        :returns: cantidad de reglas evaluadas.
        """
        from apps.movimientos.models import Existencia  # pylint: disable=import-outside-toplevel

        pares = list(dict.fromkeys(pares))
        if not pares:
            return 0

        reglas = list(
            RepositorioReglas.listar(solo_activas=True).exclude(tipo=TipoRegla.VENCIMIENTO_PROXIMO)
        )
        if not reglas:
            return 0
        almacenes_por_regla = {r.pk: set(r.almacenes.values_list("id", flat=True)) for r in reglas}
        categorias_por_regla = {r.pk: set(r.categorias.values_list("id", flat=True)) for r in reglas}

        contadas = 0
        for articulo_id, almacen_id in pares:
            existencia = Existencia.objects.select_related("articulo", "almacen").filter(
                articulo_id=articulo_id, almacen_id=almacen_id
            ).first()
            if existencia is None:
                continue
            for regla in reglas:
                if not _regla_aplica(
                    regla, existencia.articulo, almacen_id, almacenes_por_regla, categorias_por_regla
                ):
                    continue
                contadas += 1
                if regla.tipo in (TipoRegla.STOCK_BAJO, TipoRegla.STOCK_CERO):
                    _evaluar_stock(regla, existencia)
                elif regla.tipo == TipoRegla.SIN_MOVIMIENTO:
                    _evaluar_sin_movimiento(regla, existencia)
        return contadas

    @staticmethod
    @transaction.atomic
    def evaluar_todo() -> int:
        """
        Recorre todas las reglas activas contra todo el inventario.

        Se usa desde el botón «Evaluar ahora» y desde el comando de gestión
        ``evaluar_alertas``, pensado para un ping externo — el plan gratuito
        de Render no trae tareas programadas.

        :returns: cantidad de reglas evaluadas.
        """
        from apps.movimientos.models import Existencia  # pylint: disable=import-outside-toplevel

        reglas = list(RepositorioReglas.listar(solo_activas=True))
        contadas = 0
        existencias = Existencia.objects.select_related("articulo", "almacen").all()
        almacenes_por_regla = {r.pk: set(r.almacenes.values_list("id", flat=True)) for r in reglas}
        categorias_por_regla = {r.pk: set(r.categorias.values_list("id", flat=True)) for r in reglas}

        for regla in reglas:
            if regla.tipo == TipoRegla.VENCIMIENTO_PROXIMO:
                _evaluar_vencimiento(regla)
                contadas += 1
                continue
            for existencia in existencias:
                if not _regla_aplica(
                    regla, existencia.articulo, existencia.almacen_id,
                    almacenes_por_regla, categorias_por_regla,
                ):
                    continue
                contadas += 1
                if regla.tipo in (TipoRegla.STOCK_BAJO, TipoRegla.STOCK_CERO):
                    _evaluar_stock(regla, existencia)
                elif regla.tipo == TipoRegla.SIN_MOVIMIENTO:
                    _evaluar_sin_movimiento(regla, existencia)
        return contadas
