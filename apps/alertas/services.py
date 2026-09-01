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


class _Pendientes:
    """
    Junta lo que una pasada de evaluación decidió, y lo escribe de una vez.

    El evaluador antes preguntaba a la base por cada par (artículo, almacén)
    para saber si ya había una alerta abierta, y volvía a escribir de a una.
    Con la base en otra región eso eran miles de idas y vueltas. Ahora las
    alertas vivas se leen una sola vez, se decide en memoria, y aquí se
    acumulan las altas, las modificaciones y los cierres.
    """

    def __init__(self, abiertas: dict[tuple[int, int, int], Alerta]) -> None:
        self._abiertas = abiertas
        self._nuevas: list[Alerta] = []
        self._a_actualizar: list[Alerta] = []
        self._a_cerrar: list[int] = []

    def registrar(self, regla_id: int, articulo_id: int, almacen_id: int,
                  decision: tuple[str, dict] | None) -> None:
        """
        Anota qué hacer con un par ya evaluado.

        :param decision: ``(mensaje, contexto)`` si la alerta debe estar
            abierta, o ``None`` si debe cerrarse.
        """
        existente = self._abiertas.get((regla_id, articulo_id, almacen_id))

        if decision is None:
            if existente is not None:
                self._a_cerrar.append(existente.pk)
            return

        mensaje, contexto = decision
        if existente is None:
            self._nuevas.append(
                Alerta(
                    regla_id=regla_id, articulo_id=articulo_id, almacen_id=almacen_id,
                    mensaje=mensaje, contexto=contexto,
                )
            )
        elif existente.mensaje != mensaje or existente.contexto != contexto:
            existente.mensaje = mensaje
            existente.contexto = contexto
            self._a_actualizar.append(existente)

    def cerrar_par(self, regla_id: int, articulo_id: int, almacen_id: int) -> None:
        """Cierra un par sin evaluarlo — lo usa la regla de vencimiento."""
        self.registrar(regla_id, articulo_id, almacen_id, None)

    def escribir(self) -> None:
        """Vuelca a la base lo acumulado: como mucho tres consultas."""
        momento = timezone.now()
        if self._nuevas:
            RepositorioAlertas.crear_muchas(self._nuevas)
        if self._a_actualizar:
            for alerta in self._a_actualizar:
                alerta.actualizado_en = momento
            RepositorioAlertas.actualizar_mensajes(self._a_actualizar)
        if self._a_cerrar:
            RepositorioAlertas.cerrar_muchas(self._a_cerrar, momento)


def _decidir_stock(regla: ReglaAlerta, existencia) -> tuple[str, dict] | None:
    """Decide si una existencia incumple una regla de existencia (bajo mínimo o en cero)."""
    if regla.tipo == TipoRegla.STOCK_CERO:
        if existencia.cantidad <= 0:
            return (
                f"{existencia.articulo.sku} está en cero en {existencia.almacen.codigo}.",
                {"cantidad": str(existencia.cantidad)},
            )
        return None

    if 0 < existencia.cantidad < existencia.stock_minimo:
        return (
            f"{existencia.articulo.sku} tiene {existencia.cantidad} unidades en "
            f"{existencia.almacen.codigo}, por debajo del mínimo ({existencia.stock_minimo}).",
            {"cantidad": str(existencia.cantidad), "minimo": str(existencia.stock_minimo)},
        )
    return None


def _decidir_sin_movimiento(regla: ReglaAlerta, existencia, ahora) -> tuple[str, dict] | None:
    """Decide si un artículo lleva demasiado tiempo quieto en un almacén."""
    limite = ahora - timedelta(days=regla.dias_umbral)
    sin_movimiento = (
        existencia.ultimo_movimiento_en is None or existencia.ultimo_movimiento_en < limite
    )
    if not (sin_movimiento and existencia.cantidad > 0):
        return None

    dias = (
        (ahora - existencia.ultimo_movimiento_en).days
        if existencia.ultimo_movimiento_en else None
    )
    return (
        f"{existencia.articulo.sku} no tiene movimientos en {existencia.almacen.codigo} "
        f"desde hace {dias if dias is not None else 'siempre'} días.",
        {"dias_sin_movimiento": dias},
    )


def _decidir(regla: ReglaAlerta, existencia, ahora) -> tuple[str, dict] | None:
    """Despacha una existencia que ya pasó el filtro de alcance a su evaluador de tipo."""
    if regla.tipo in (TipoRegla.STOCK_BAJO, TipoRegla.STOCK_CERO):
        return _decidir_stock(regla, existencia)
    if regla.tipo == TipoRegla.SIN_MOVIMIENTO:
        return _decidir_sin_movimiento(regla, existencia, ahora)
    return None


def _evaluar_vencimiento(regla: ReglaAlerta, almacenes_por_regla: dict,
                         categorias_por_regla: dict, pendientes: _Pendientes) -> None:
    """Evalúa los lotes con saldo que vencen dentro del margen de la regla."""
    from apps.movimientos.repositories import RepositorioLotes  # pylint: disable=import-outside-toplevel

    pares_vigentes = set()
    for lote in RepositorioLotes.por_vencer(regla.dias_umbral):
        if not _regla_aplica(
            regla, lote.articulo, lote.almacen_id, almacenes_por_regla, categorias_por_regla
        ):
            continue
        pares_vigentes.add((lote.articulo_id, lote.almacen_id))
        pendientes.registrar(
            regla.pk, lote.articulo_id, lote.almacen_id,
            (
                f"El lote {lote.codigo} de {lote.articulo.sku} vence el "
                f"{lote.fecha_vencimiento:%d/%m/%Y}.",
                {"lote": lote.codigo, "vencimiento": lote.fecha_vencimiento.isoformat()},
            ),
        )

    pares_abiertos = RepositorioAlertas.pares_abiertos_de_regla(regla.pk)
    for articulo_id, almacen_id in pares_abiertos - pares_vigentes:
        pendientes.cerrar_par(regla.pk, articulo_id, almacen_id)


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

        # El «exclude» se aplica en Python y no sobre el conjunto de consulta:
        # clonarlo descartaría el prefetch de almacenes y categorías que el
        # repositorio ya trajo, y volvería a preguntarlos por cada regla.
        reglas = [
            regla for regla in RepositorioReglas.listar(solo_activas=True)
            if regla.tipo != TipoRegla.VENCIMIENTO_PROXIMO
        ]
        if not reglas:
            return 0
        almacenes_por_regla = {r.pk: {a.pk for a in r.almacenes.all()} for r in reglas}
        categorias_por_regla = {r.pk: {c.pk for c in r.categorias.all()} for r in reglas}

        existencias_por_par = {
            (existencia.articulo_id, existencia.almacen_id): existencia
            for existencia in Existencia.objects.select_related("articulo", "almacen").filter(
                articulo_id__in={articulo_id for articulo_id, _ in pares},
                almacen_id__in={almacen_id for _, almacen_id in pares},
            )
        }

        pendientes = _Pendientes(
            RepositorioAlertas.abiertas_de_reglas([r.pk for r in reglas])
        )
        ahora = timezone.now()
        contadas = 0
        for articulo_id, almacen_id in pares:
            existencia = existencias_por_par.get((articulo_id, almacen_id))
            if existencia is None:
                continue
            for regla in reglas:
                if not _regla_aplica(
                    regla, existencia.articulo, almacen_id, almacenes_por_regla, categorias_por_regla
                ):
                    continue
                contadas += 1
                pendientes.registrar(
                    regla.pk, articulo_id, almacen_id, _decidir(regla, existencia, ahora)
                )
        pendientes.escribir()
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
        if not reglas:
            return 0

        contadas = 0
        # Una sola lectura del inventario: la lista se recorre una vez por
        # regla, pero el conjunto de consulta ya quedó en memoria.
        existencias = list(Existencia.objects.select_related("articulo", "almacen").all())
        # «.all()» consume el prefetch del repositorio; «.values_list()» lo
        # descartaría y volvería a consultar por cada regla.
        almacenes_por_regla = {r.pk: {a.pk for a in r.almacenes.all()} for r in reglas}
        categorias_por_regla = {r.pk: {c.pk for c in r.categorias.all()} for r in reglas}

        pendientes = _Pendientes(
            RepositorioAlertas.abiertas_de_reglas([r.pk for r in reglas])
        )
        ahora = timezone.now()

        for regla in reglas:
            if regla.tipo == TipoRegla.VENCIMIENTO_PROXIMO:
                _evaluar_vencimiento(
                    regla, almacenes_por_regla, categorias_por_regla, pendientes
                )
                contadas += 1
                continue
            for existencia in existencias:
                if not _regla_aplica(
                    regla, existencia.articulo, existencia.almacen_id,
                    almacenes_por_regla, categorias_por_regla,
                ):
                    continue
                contadas += 1
                pendientes.registrar(
                    regla.pk, existencia.articulo_id, existencia.almacen_id,
                    _decidir(regla, existencia, ahora),
                )
        pendientes.escribir()
        return contadas
