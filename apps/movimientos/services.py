"""
Servicios de Movimientos: el núcleo de mayor riesgo del sistema.

``ServicioMovimientos`` concentra la aritmética del inventario. Cada línea de
un movimiento confirmado se aplica en el mismo paso en que se crea — no
existen líneas «a medio escribir» — y solo un movimiento cuyo tipo exige
aprobación queda en ``PENDIENTE`` con su intención guardada en
``lineas_solicitadas``, sin tocar lotes ni existencias hasta que
``ServicioAprobaciones`` la confirme o la rechace.

La reversión (``anular``) nunca borra: crea un movimiento contrapartida cuyas
líneas deshacen, una por una, el efecto de las líneas originales.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalogo.repositories import RepositorioArticulos
from apps.configuracion.services import ServicioParametros
from apps.movimientos.models import (
    ConsumoLote,
    EstadoMovimiento,
    Existencia,
    Lote,
    Movimiento,
    MovimientoLinea,
    Naturaleza,
    TipoMovimiento,
)
from apps.movimientos.repositories import (
    RepositorioConsumos,
    RepositorioExistencias,
    RepositorioKardex,
    RepositorioLotes,
    RepositorioMovimientos,
    RepositorioTiposMovimiento,
)
from apps.movimientos.valoracion import (
    CUATRO_DECIMALES,
    METODO_PEPS,
    costo_total_del_plan,
    costo_unitario_promedio_del_plan,
    orden_de_consumo,
    planificar_consumo,
)
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria


def _decimal(valor: Any) -> Decimal:
    """Convierte de forma segura un valor de formulario o JSON a ``Decimal``."""
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES)


def _a_fecha(valor: Any) -> date | None:
    """Convierte a ``date`` un valor que puede venir ya así o como texto ISO (desde JSON)."""
    if not valor:
        return None
    return date.fromisoformat(valor) if isinstance(valor, str) else valor


def _serializar_lineas(lineas: list[dict]) -> list[dict]:
    """
    Convierte una lista de líneas a tipos que ``JSONField`` puede guardar.

    Solo hace falta para un movimiento que queda ``PENDIENTE``: mientras
    espera aprobación, su intención se guarda tal cual — ``Decimal`` y
    ``date`` no son JSON válido, así que se pasan a texto aquí y se
    reconstruyen en :meth:`ServicioAprobaciones.aprobar`.
    """
    serializadas = []
    for linea in lineas:
        copia = dict(linea)
        for clave in ("cantidad", "costo_unitario"):
            if copia.get(clave) is not None:
                copia[clave] = str(copia[clave])
        if copia.get("fecha_vencimiento"):
            copia["fecha_vencimiento"] = copia["fecha_vencimiento"].isoformat()
        serializadas.append(copia)
    return serializadas


class ServicioTiposMovimiento:
    """Alta y edición de los tipos de movimiento configurables."""

    @staticmethod
    def listar(solo_activos: bool = False) -> Any:
        """Devuelve los tipos de movimiento."""
        return RepositorioTiposMovimiento.listar(solo_activos=solo_activos)

    @staticmethod
    def obtener(tipo_id: int) -> TipoMovimiento | None:
        """Devuelve un tipo de movimiento por su identificador."""
        return RepositorioTiposMovimiento.obtener(tipo_id)

    @staticmethod
    @transaction.atomic
    def crear(**datos) -> TipoMovimiento:
        """
        Crea un tipo de movimiento.

        :raises ValidationError: si el código ya existe.
        """
        codigo = datos["codigo"].strip().upper()
        if RepositorioTiposMovimiento.existe_codigo(codigo):
            raise ValidationError({"codigo": "Ya existe un tipo de movimiento con ese código."})

        tipo = TipoMovimiento.objects.create(
            codigo=codigo,
            nombre=datos["nombre"].strip(),
            naturaleza=datos["naturaleza"],
            prefijo_numeracion=(datos.get("prefijo_numeracion") or codigo).strip().upper(),
            exige_documento=datos.get("exige_documento", False),
            exige_ncf=datos.get("exige_ncf", False),
            exige_motivo=datos.get("exige_motivo", False),
            exige_aprobacion=datos.get("exige_aprobacion", False),
            permite_anulacion=datos.get("permite_anulacion", True),
            tipo_contrapartida=datos.get("tipo_contrapartida"),
            color=datos.get("color") or "#6A665F",
            orden=datos.get("orden") or 10,
            activo=datos.get("activo", True),
        )
        ServicioAuditoria.registrar(
            entidad="TipoMovimiento", entidad_id=tipo.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"codigo": tipo.codigo, "naturaleza": tipo.naturaleza},
        )
        return tipo

    @staticmethod
    @transaction.atomic
    def actualizar(tipo: TipoMovimiento, **datos) -> TipoMovimiento:
        """Actualiza un tipo de movimiento. El código y la naturaleza no se tocan aquí."""
        for campo in (
            "nombre", "prefijo_numeracion", "exige_documento", "exige_ncf", "exige_motivo",
            "exige_aprobacion", "permite_anulacion", "tipo_contrapartida", "color", "orden",
            "activo",
        ):
            if campo in datos:
                valor = datos[campo]
                setattr(tipo, campo, valor.strip() if isinstance(valor, str) else valor)
        tipo.save()
        ServicioAuditoria.registrar(
            entidad="TipoMovimiento", entidad_id=tipo.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"codigo": tipo.codigo},
        )
        return tipo


def _validar_naturaleza(tipo: TipoMovimiento, esperada: str) -> None:
    """Impide registrar, por ejemplo, una entrada con un tipo configurado como salida."""
    if tipo.naturaleza != esperada:
        raise ValidationError(
            f"El tipo «{tipo.nombre}» es de naturaleza «{tipo.get_naturaleza_display()}», "
            f"no se puede usar aquí."
        )


def _bloquear_existencias_en_orden(pares: set[tuple[int, int]]) -> None:
    """
    Bloquea las filas de existencia tocadas por el movimiento en un orden
    determinista (por articulo_id, almacen_id), para que dos movimientos
    concurrentes que tocan los mismos pares nunca se interbloqueen.
    """
    for articulo_id, almacen_id in sorted(pares):
        RepositorioExistencias.bloqueada(articulo_id, almacen_id)


def _aplicar_linea_entrada(
    movimiento: Movimiento, articulo_id: int, almacen_id: int, cantidad: Decimal,
    costo_unitario: Decimal, indice: int, numero_lote: str = "",
    fecha_vencimiento: date | None = None, notas: str = "",
) -> tuple[MovimientoLinea, Decimal]:
    """Crea la línea de entrada, su lote y actualiza la existencia. Devuelve (línea, costo_total)."""
    existencia = RepositorioExistencias.bloqueada(articulo_id, almacen_id)
    costo_total = (cantidad * costo_unitario).quantize(CUATRO_DECIMALES)
    saldo_posterior = existencia.cantidad + cantidad

    linea = MovimientoLinea.objects.create(
        movimiento=movimiento, articulo_id=articulo_id, almacen_id=almacen_id, signo=1,
        cantidad=cantidad, costo_unitario=costo_unitario, costo_total=costo_total,
        saldo_posterior=saldo_posterior, notas=notas,
    )
    codigo_lote = (numero_lote or "").strip() or f"{movimiento.numero}-{indice}"
    Lote.objects.create(
        codigo=codigo_lote, articulo_id=articulo_id, almacen_id=almacen_id,
        linea_origen=linea, costo_unitario=costo_unitario, cantidad_inicial=cantidad,
        cantidad_disponible=cantidad, recibido_en=movimiento.fecha,
        fecha_vencimiento=fecha_vencimiento,
    )
    existencia.cantidad = saldo_posterior
    existencia.valor = existencia.valor + costo_total
    existencia.ultimo_movimiento_en = timezone.now()
    existencia.save()
    return linea, costo_total


def _aplicar_linea_salida(
    movimiento: Movimiento, articulo_id: int, almacen_id: int, cantidad: Decimal,
    metodo: str, notas: str = "",
) -> tuple[MovimientoLinea, Decimal, list]:
    """
    Consume lotes según ``metodo``, crea la línea de salida y sus consumos.

    :raises ValidationError: si la existencia no alcanza y el parámetro
        ``permitir_stock_negativo`` no lo autoriza.
    :returns: la línea creada, el costo total consumido y el plan de consumo
        (lo último lo usa ``_aplicar_linea_transferencia`` para replicar el
        costo de cada lote en el almacén de destino).
    """
    existencia = RepositorioExistencias.bloqueada(articulo_id, almacen_id)
    permitir_negativo = ServicioParametros.obtener("permitir_stock_negativo", False)
    if existencia.cantidad - cantidad < 0 and not permitir_negativo:
        raise ValidationError(
            f"No hay existencia suficiente (disponible: {existencia.cantidad})."
        )

    orden = orden_de_consumo(metodo)
    lotes = list(RepositorioLotes.disponibles_bloqueados(articulo_id, almacen_id, orden))
    plan = planificar_consumo(lotes, cantidad, metodo, existencia.costo_promedio)
    costo_total = costo_total_del_plan(plan)
    saldo_posterior = existencia.cantidad - cantidad

    linea = MovimientoLinea.objects.create(
        movimiento=movimiento, articulo_id=articulo_id, almacen_id=almacen_id, signo=-1,
        cantidad=cantidad, costo_unitario=costo_unitario_promedio_del_plan(plan),
        costo_total=costo_total, saldo_posterior=saldo_posterior, notas=notas,
    )
    for item in plan:
        if item.lote is not None:
            item.lote.cantidad_disponible = item.lote.cantidad_disponible - item.cantidad
            item.lote.save(update_fields=["cantidad_disponible", "actualizado_en"])
        ConsumoLote.objects.create(
            linea=linea, lote=item.lote, cantidad=item.cantidad, costo_unitario=item.costo_unitario,
        )
    existencia.cantidad = saldo_posterior
    existencia.valor = existencia.valor - costo_total
    existencia.ultimo_movimiento_en = timezone.now()
    existencia.save()
    return linea, costo_total, plan


def _aplicar_linea_transferencia(
    movimiento: Movimiento, articulo_id: int, almacen_origen_id: int, almacen_destino_id: int,
    cantidad: Decimal, metodo: str, indice: int,
) -> Decimal:
    """Consume en el origen y crea, por cada lote consumido, un lote gemelo en el destino."""
    _, costo_total_origen, plan = _aplicar_linea_salida(
        movimiento, articulo_id, almacen_origen_id, cantidad, metodo,
        notas="Transferencia — sale hacia otro almacén.",
    )

    existencia_destino = RepositorioExistencias.bloqueada(articulo_id, almacen_destino_id)
    saldo_destino = existencia_destino.cantidad
    valor_agregado = Decimal("0")
    for sub_indice, item in enumerate(plan, start=1):
        saldo_destino += item.cantidad
        linea_entrada = MovimientoLinea.objects.create(
            movimiento=movimiento, articulo_id=articulo_id, almacen_id=almacen_destino_id,
            signo=1, cantidad=item.cantidad, costo_unitario=item.costo_unitario,
            costo_total=item.costo_total, saldo_posterior=saldo_destino,
            notas="Transferencia — conserva el costo del lote de origen.",
        )
        Lote.objects.create(
            codigo=f"{movimiento.numero}-{indice}-{sub_indice}", articulo_id=articulo_id,
            almacen_id=almacen_destino_id, linea_origen=linea_entrada,
            costo_unitario=item.costo_unitario, cantidad_inicial=item.cantidad,
            cantidad_disponible=item.cantidad, recibido_en=movimiento.fecha,
        )
        valor_agregado += item.costo_total

    existencia_destino.cantidad = saldo_destino
    existencia_destino.valor = existencia_destino.valor + valor_agregado
    existencia_destino.ultimo_movimiento_en = timezone.now()
    existencia_destino.save()
    return costo_total_origen


def _crear_cabecera(tipo: TipoMovimiento, naturaleza: str, usuario, **campos) -> Movimiento:
    """Reserva el número del tipo y crea la cabecera del movimiento, en borrador."""
    secuencia = RepositorioMovimientos.siguiente_secuencia(tipo)
    numero = f"{tipo.prefijo_numeracion}-{secuencia:06d}"
    return Movimiento.objects.create(
        numero=numero, tipo=tipo, naturaleza=naturaleza, usuario=usuario, **campos
    )


def _registrar_y_aplicar(
    movimiento: Movimiento, lineas_solicitadas: list[dict], aplicar: Any,
) -> Movimiento:
    """
    Deja el movimiento listo: aplicado de inmediato si su tipo no exige
    aprobación, o guardado como intención pendiente si sí la exige.

    :param aplicar: función que recorre ``lineas_solicitadas`` y aplica sus
        efectos sobre ``movimiento`` (crea líneas, lotes, consumos y
        actualiza existencias), devolviendo ``(total_cantidad, total_costo)``.
    """
    if movimiento.tipo.exige_aprobacion:
        movimiento.lineas_solicitadas = _serializar_lineas(lineas_solicitadas)
        movimiento.estado = EstadoMovimiento.PENDIENTE
        movimiento.save()
        return movimiento

    movimiento.metodo_valoracion = ServicioParametros.obtener("metodo_valoracion", METODO_PEPS)
    total_cantidad, total_costo = aplicar(movimiento, lineas_solicitadas)
    movimiento.estado = EstadoMovimiento.CONFIRMADO
    movimiento.total_cantidad = total_cantidad
    movimiento.total_costo = total_costo
    movimiento.save()
    _evaluar_alertas_del_movimiento(movimiento)
    return movimiento


def _evaluar_alertas_del_movimiento(movimiento: Movimiento) -> None:
    """
    Dispara la evaluación de alertas sobre los pares (artículo, almacén) que
    tocó el movimiento — así una entrada o salida se refleja en la bandeja de
    alertas sin esperar a una tarea programada (el plan gratuito de Render no
    trae una).
    """
    from apps.alertas.services import ServicioEvaluador  # pylint: disable=import-outside-toplevel

    pares = set(movimiento.lineas.values_list("articulo_id", "almacen_id"))
    if pares:
        ServicioEvaluador.evaluar_pares(pares)


def _aplicar_lineas_entrada(movimiento: Movimiento, lineas: list[dict]) -> tuple[Decimal, Decimal]:
    total_cantidad = Decimal("0")
    total_costo = Decimal("0")
    for indice, linea in enumerate(lineas, start=1):
        _, costo_total = _aplicar_linea_entrada(
            movimiento, linea["articulo_id"], movimiento.almacen_destino_id,
            _decimal(linea["cantidad"]), _decimal(linea["costo_unitario"]), indice,
            numero_lote=linea.get("numero_lote", ""),
            fecha_vencimiento=_a_fecha(linea.get("fecha_vencimiento")),
        )
        total_cantidad += _decimal(linea["cantidad"])
        total_costo += costo_total
    return total_cantidad, total_costo


def _aplicar_lineas_salida(movimiento: Movimiento, lineas: list[dict]) -> tuple[Decimal, Decimal]:
    total_cantidad = Decimal("0")
    total_costo = Decimal("0")
    for linea in lineas:
        _, costo_total, _plan = _aplicar_linea_salida(
            movimiento, linea["articulo_id"], movimiento.almacen_origen_id,
            _decimal(linea["cantidad"]), movimiento.metodo_valoracion,
        )
        total_cantidad += _decimal(linea["cantidad"])
        total_costo += costo_total
    return total_cantidad, total_costo


def _aplicar_lineas_transferencia(movimiento: Movimiento, lineas: list[dict]) -> tuple[Decimal, Decimal]:
    total_cantidad = Decimal("0")
    total_costo = Decimal("0")
    for indice, linea in enumerate(lineas, start=1):
        costo_total = _aplicar_linea_transferencia(
            movimiento, linea["articulo_id"], movimiento.almacen_origen_id,
            movimiento.almacen_destino_id, _decimal(linea["cantidad"]),
            movimiento.metodo_valoracion, indice,
        )
        total_cantidad += _decimal(linea["cantidad"])
        total_costo += costo_total
    return total_cantidad, total_costo


def _aplicar_lineas_ajuste(movimiento: Movimiento, lineas: list[dict]) -> tuple[Decimal, Decimal]:
    total_cantidad = Decimal("0")
    total_costo = Decimal("0")
    for indice, linea in enumerate(lineas, start=1):
        cantidad = _decimal(linea["cantidad"])
        if int(linea["signo"]) >= 0:
            costo_unitario_provisto = linea.get("costo_unitario")
            if costo_unitario_provisto is None:
                existencia = Existencia.objects.filter(
                    articulo_id=linea["articulo_id"], almacen_id=movimiento.almacen_origen_id
                ).first()
                costo_unitario = existencia.costo_promedio if existencia else Decimal("0")
            else:
                costo_unitario = _decimal(costo_unitario_provisto)
            _, costo_total = _aplicar_linea_entrada(
                movimiento, linea["articulo_id"], movimiento.almacen_origen_id, cantidad,
                costo_unitario, indice, notas="Ajuste — existencia encontrada.",
            )
        else:
            _, costo_total, _plan = _aplicar_linea_salida(
                movimiento, linea["articulo_id"], movimiento.almacen_origen_id, cantidad,
                movimiento.metodo_valoracion, notas="Ajuste — existencia faltante.",
            )
        total_cantidad += cantidad
        total_costo += costo_total
    return total_cantidad, total_costo


class ServicioMovimientos:
    """Registro, consulta y anulación de movimientos de inventario."""

    @staticmethod
    def listar(**filtros) -> Any:
        """Devuelve los movimientos filtrados."""
        return RepositorioMovimientos.listar(**filtros)

    @staticmethod
    def obtener(movimiento_id: int) -> Movimiento | None:
        """Devuelve un movimiento con sus relaciones precargadas."""
        return RepositorioMovimientos.obtener(movimiento_id)

    @staticmethod
    def kardex_de(articulo_id: int, almacen_id: int | None = None) -> Any:
        """Devuelve el historial cronológico de un artículo."""
        return RepositorioKardex.lineas_de(articulo_id, almacen_id)

    @staticmethod
    def existencias(**filtros) -> Any:
        """Devuelve las existencias filtradas."""
        return RepositorioExistencias.listar(**filtros)

    @staticmethod
    def lineas_solicitadas_para_mostrar(movimiento: Movimiento) -> dict:
        """
        Resuelve ``lineas_solicitadas`` a algo que la ficha pueda pintar,
        para un movimiento todavía ``PENDIENTE``.

        La entrada trae su propio costo (lo escribió quien la registró); la
        salida, la transferencia y el ajuste sin costo explícito no lo
        tienen todavía — el costo real depende de qué lotes se consuman, y
        eso solo se sabe al aprobar. Para esas líneas se muestra el costo
        promedio actual como estimado, marcado como tal, para que quien
        aprueba no vea un total en cero.

        :returns: ``{"lineas": [...], "total_cantidad": Decimal,
            "total_costo": Decimal, "costo_estimado": bool}``
        """
        almacen_id = (
            movimiento.almacen_destino_id
            if movimiento.naturaleza == Naturaleza.ENTRADA
            else movimiento.almacen_origen_id
        )
        lineas = []
        total_cantidad = Decimal("0")
        total_costo = Decimal("0")
        costo_estimado = False

        for solicitada in movimiento.lineas_solicitadas:
            articulo = RepositorioArticulos.obtener(solicitada["articulo_id"])
            cantidad = _decimal(solicitada["cantidad"])
            costo_provisto = solicitada.get("costo_unitario")
            if costo_provisto is not None:
                costo_unitario = _decimal(costo_provisto)
                es_estimado = False
            else:
                existencia = next(
                    (
                        e for e in RepositorioExistencias.de_articulo(solicitada["articulo_id"])
                        if e.almacen_id == almacen_id
                    ),
                    None,
                )
                costo_unitario = existencia.costo_promedio if existencia else Decimal("0")
                es_estimado = True
                costo_estimado = True

            costo_total = (cantidad * costo_unitario).quantize(CUATRO_DECIMALES)
            lineas.append({
                "articulo": articulo, "cantidad": cantidad, "costo_unitario": costo_unitario,
                "costo_total": costo_total, "signo": solicitada.get("signo", 1),
                "estimado": es_estimado,
            })
            total_cantidad += cantidad
            total_costo += costo_total

        return {
            "lineas": lineas, "total_cantidad": total_cantidad, "total_costo": total_costo,
            "costo_estimado": costo_estimado,
        }

    @staticmethod
    @transaction.atomic
    def registrar_entrada(
        tipo: TipoMovimiento, almacen_destino, usuario, lineas: list[dict],
        fecha=None, proveedor=None, documento_tipo: str = "", documento_numero: str = "",
        ncf: str = "", fecha_documento=None, motivo: str = "", observaciones: str = "",
    ) -> Movimiento:
        """
        Registra una entrada de inventario. Cada línea de ``lineas`` crea su
        propio lote.

        :raises ValidationError: si el tipo no es de naturaleza «entrada», si
            faltan datos que el tipo exige, si el NCF ya se usó con ese
            proveedor, o si la lista de líneas está vacía.
        """
        _validar_naturaleza(tipo, Naturaleza.ENTRADA)
        if not lineas:
            raise ValidationError("La entrada necesita al menos una línea.")
        if tipo.exige_documento and not documento_numero.strip():
            raise ValidationError({"documento_numero": "Este tipo exige número de documento."})
        if tipo.exige_ncf and not ncf.strip():
            raise ValidationError({"ncf": "Este tipo exige comprobante fiscal (NCF)."})
        if ncf and proveedor and RepositorioMovimientos.existe_ncf(proveedor.pk, ncf):
            raise ValidationError({"ncf": "Ese proveedor ya tiene registrado ese NCF."})

        pares = {(linea["articulo_id"], almacen_destino.pk) for linea in lineas}
        _bloquear_existencias_en_orden(pares)

        movimiento = _crear_cabecera(
            tipo, Naturaleza.ENTRADA, usuario, almacen_destino=almacen_destino,
            fecha=fecha or timezone.now(), proveedor=proveedor, documento_tipo=documento_tipo,
            documento_numero=documento_numero, ncf=ncf, fecha_documento=fecha_documento,
            motivo=motivo, observaciones=observaciones,
        )
        movimiento = _registrar_y_aplicar(movimiento, lineas, _aplicar_lineas_entrada)
        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"numero": movimiento.numero, "tipo": tipo.codigo, "estado": movimiento.estado},
        )
        return movimiento

    @staticmethod
    @transaction.atomic
    def registrar_salida(
        tipo: TipoMovimiento, almacen_origen, usuario, lineas: list[dict],
        fecha=None, cliente=None, documento_tipo: str = "", documento_numero: str = "",
        motivo: str = "", observaciones: str = "",
    ) -> Movimiento:
        """
        Registra una salida de inventario, consumiendo lotes según el método
        de valoración vigente.

        :raises ValidationError: si el tipo no es de naturaleza «salida», si
            la lista de líneas está vacía, o si la existencia no alcanza.
        """
        _validar_naturaleza(tipo, Naturaleza.SALIDA)
        if not lineas:
            raise ValidationError("La salida necesita al menos una línea.")
        if tipo.exige_documento and not documento_numero.strip():
            raise ValidationError({"documento_numero": "Este tipo exige número de documento."})

        pares = {(linea["articulo_id"], almacen_origen.pk) for linea in lineas}
        _bloquear_existencias_en_orden(pares)

        movimiento = _crear_cabecera(
            tipo, Naturaleza.SALIDA, usuario, almacen_origen=almacen_origen,
            fecha=fecha or timezone.now(), cliente=cliente, documento_tipo=documento_tipo,
            documento_numero=documento_numero, motivo=motivo, observaciones=observaciones,
        )
        movimiento = _registrar_y_aplicar(movimiento, lineas, _aplicar_lineas_salida)
        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"numero": movimiento.numero, "tipo": tipo.codigo, "estado": movimiento.estado},
        )
        return movimiento

    @staticmethod
    @transaction.atomic
    def registrar_transferencia(
        tipo: TipoMovimiento, almacen_origen, almacen_destino, usuario, lineas: list[dict],
        fecha=None, motivo: str = "", observaciones: str = "",
    ) -> Movimiento:
        """
        Registra una transferencia entre almacenes, conservando el costo de
        cada lote de origen en los lotes que crea del lado del destino.

        :raises ValidationError: si el tipo no es de naturaleza «transferencia»,
            si origen y destino son el mismo almacén, o si la lista de líneas
            está vacía.
        """
        _validar_naturaleza(tipo, Naturaleza.TRANSFERENCIA)
        if almacen_origen.pk == almacen_destino.pk:
            raise ValidationError("El almacén de origen y el de destino deben ser distintos.")
        if not lineas:
            raise ValidationError("La transferencia necesita al menos una línea.")

        pares = {(linea["articulo_id"], almacen_origen.pk) for linea in lineas} | {
            (linea["articulo_id"], almacen_destino.pk) for linea in lineas
        }
        _bloquear_existencias_en_orden(pares)

        movimiento = _crear_cabecera(
            tipo, Naturaleza.TRANSFERENCIA, usuario, almacen_origen=almacen_origen,
            almacen_destino=almacen_destino, fecha=fecha or timezone.now(),
            motivo=motivo, observaciones=observaciones,
        )
        movimiento = _registrar_y_aplicar(movimiento, lineas, _aplicar_lineas_transferencia)
        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"numero": movimiento.numero, "tipo": tipo.codigo, "estado": movimiento.estado},
        )
        return movimiento

    @staticmethod
    @transaction.atomic
    def registrar_ajuste(
        tipo: TipoMovimiento, almacen, usuario, lineas: list[dict], motivo: str,
        fecha=None, observaciones: str = "",
    ) -> Movimiento:
        """
        Registra un ajuste de inventario. Cada línea trae su propio
        ``signo``: positivo para existencia encontrada, negativo para
        existencia faltante.

        :raises ValidationError: si el tipo no es de naturaleza «ajuste», si
            falta el motivo (obligatorio sin excepción para esta operación),
            o si la lista de líneas está vacía.
        """
        _validar_naturaleza(tipo, Naturaleza.AJUSTE)
        if not motivo.strip():
            raise ValidationError({"motivo": "Todo ajuste necesita un motivo."})
        if not lineas:
            raise ValidationError("El ajuste necesita al menos una línea.")

        pares = {(linea["articulo_id"], almacen.pk) for linea in lineas}
        _bloquear_existencias_en_orden(pares)

        movimiento = _crear_cabecera(
            tipo, Naturaleza.AJUSTE, usuario, almacen_origen=almacen,
            fecha=fecha or timezone.now(), motivo=motivo, observaciones=observaciones,
        )
        movimiento = _registrar_y_aplicar(movimiento, lineas, _aplicar_lineas_ajuste)
        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"numero": movimiento.numero, "tipo": tipo.codigo, "estado": movimiento.estado,
                    "motivo": motivo},
        )
        return movimiento

    @staticmethod
    def _deshacer_linea(
        contrapartida: Movimiento, linea_original: MovimientoLinea
    ) -> tuple[Decimal, Decimal]:
        """Aplica, sobre ``contrapartida``, el efecto inverso de una línea original."""
        existencia = RepositorioExistencias.bloqueada(
            linea_original.articulo_id, linea_original.almacen_id
        )
        cantidad = linea_original.cantidad
        costo_total = linea_original.costo_total

        if linea_original.signo == 1:
            lote = Lote.objects.select_for_update().filter(linea_origen=linea_original).first()
            if lote is None or lote.cantidad_disponible != lote.cantidad_inicial:
                raise ValidationError(
                    "El lote que creó esta línea ya fue consumido total o parcialmente; "
                    "regístre un ajuste en lugar de anular."
                )
            lote.cantidad_disponible = Decimal("0")
            lote.save(update_fields=["cantidad_disponible", "actualizado_en"])
            signo_nuevo = -1
            existencia.cantidad = existencia.cantidad - cantidad
            existencia.valor = existencia.valor - costo_total
        else:
            for consumo in RepositorioConsumos.de_linea(linea_original.pk):
                if consumo.lote_id:
                    lote = Lote.objects.select_for_update().get(pk=consumo.lote_id)
                    lote.cantidad_disponible = lote.cantidad_disponible + consumo.cantidad
                    lote.save(update_fields=["cantidad_disponible", "actualizado_en"])
            signo_nuevo = 1
            existencia.cantidad = existencia.cantidad + cantidad
            existencia.valor = existencia.valor + costo_total

        existencia.ultimo_movimiento_en = timezone.now()
        existencia.save()

        MovimientoLinea.objects.create(
            movimiento=contrapartida, articulo_id=linea_original.articulo_id,
            almacen_id=linea_original.almacen_id, signo=signo_nuevo, cantidad=cantidad,
            costo_unitario=linea_original.costo_unitario, costo_total=costo_total,
            saldo_posterior=existencia.cantidad,
            notas=f"Anulación de la línea #{linea_original.pk}.",
        )
        return cantidad, costo_total

    @staticmethod
    @transaction.atomic
    def anular(movimiento: Movimiento, motivo: str, usuario) -> Movimiento:
        """
        Anula un movimiento confirmado mediante un movimiento contrapartida
        que invierte cada una de sus líneas — nunca lo borra ni lo edita.

        :raises ValidationError: si el movimiento no está confirmado, si su
            tipo no admite anulación, si ya fue anulado antes, si no se da un
            motivo, o si alguna de sus líneas de entrada ya fue consumida
            (en ese caso corresponde un ajuste, no una anulación).
        """
        if movimiento.estado != EstadoMovimiento.CONFIRMADO:
            raise ValidationError("Solo se puede anular un movimiento confirmado.")
        if not movimiento.tipo.permite_anulacion:
            raise ValidationError("Este tipo de movimiento no admite anulación.")
        if Movimiento.objects.filter(anula=movimiento).exists():
            raise ValidationError("Este movimiento ya tiene una anulación registrada.")
        if not motivo.strip():
            raise ValidationError({"motivo_anulacion": "Indique el motivo de la anulación."})

        tipo_contra = movimiento.tipo.tipo_contrapartida or movimiento.tipo
        lineas_originales = list(movimiento.lineas.order_by("id"))
        pares = {(linea.articulo_id, linea.almacen_id) for linea in lineas_originales}
        _bloquear_existencias_en_orden(pares)

        secuencia = RepositorioMovimientos.siguiente_secuencia(tipo_contra)
        # Nace en borrador a propósito: mientras se deshacen las líneas todavía
        # no es un movimiento confirmado, así que su propio save() no cae bajo
        # la protección de inmutabilidad. Solo al final, en un único save(),
        # pasa a «confirmado» junto con sus totales ya calculados.
        contrapartida = Movimiento.objects.create(
            numero=f"{tipo_contra.prefijo_numeracion}-{secuencia:06d}", tipo=tipo_contra,
            naturaleza=movimiento.naturaleza, estado=EstadoMovimiento.BORRADOR,
            fecha=timezone.now(), almacen_origen=movimiento.almacen_origen,
            almacen_destino=movimiento.almacen_destino, usuario=usuario,
            metodo_valoracion=movimiento.metodo_valoracion, anula=movimiento,
            motivo=f"Anulación de {movimiento.numero}: {motivo.strip()}",
        )

        total_cantidad = Decimal("0")
        total_costo = Decimal("0")
        for linea_original in lineas_originales:
            cantidad, costo = ServicioMovimientos._deshacer_linea(contrapartida, linea_original)
            total_cantidad += cantidad
            total_costo += costo

        contrapartida.total_cantidad = total_cantidad
        contrapartida.total_costo = total_costo
        contrapartida.estado = EstadoMovimiento.CONFIRMADO
        contrapartida.save()

        movimiento.estado = EstadoMovimiento.ANULADO
        movimiento.anulado_en = timezone.now()
        movimiento.motivo_anulacion = motivo.strip()
        movimiento.save(
            update_fields=["estado", "anulado_en", "motivo_anulacion", "actualizado_en"]
        )
        _evaluar_alertas_del_movimiento(contrapartida)

        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "anular", "numero": movimiento.numero,
                    "contrapartida": contrapartida.numero, "motivo": motivo.strip()},
        )
        return contrapartida


_APLICADORES_POR_NATURALEZA = {
    Naturaleza.ENTRADA: _aplicar_lineas_entrada,
    Naturaleza.SALIDA: _aplicar_lineas_salida,
    Naturaleza.TRANSFERENCIA: _aplicar_lineas_transferencia,
    Naturaleza.AJUSTE: _aplicar_lineas_ajuste,
}


class ServicioAprobaciones:
    """Bandeja de movimientos pendientes: aprobarlos los aplica, rechazarlos los descarta."""

    @staticmethod
    def pendientes() -> Any:
        """Devuelve los movimientos que esperan aprobación."""
        return RepositorioMovimientos.pendientes_de_aprobacion()

    @staticmethod
    @transaction.atomic
    def aprobar(movimiento: Movimiento, usuario) -> Movimiento:
        """
        Aprueba un movimiento pendiente: recién ahora se crean sus líneas,
        lotes y consumos, y se actualiza la existencia.

        :raises ValidationError: si el movimiento no está pendiente.
        """
        if movimiento.estado != EstadoMovimiento.PENDIENTE:
            raise ValidationError("Solo se puede aprobar un movimiento pendiente.")

        pares = {
            (linea["articulo_id"], movimiento.almacen_destino_id or movimiento.almacen_origen_id)
            for linea in movimiento.lineas_solicitadas
        }
        if movimiento.naturaleza == Naturaleza.TRANSFERENCIA:
            pares |= {
                (linea["articulo_id"], movimiento.almacen_origen_id)
                for linea in movimiento.lineas_solicitadas
            }
        _bloquear_existencias_en_orden(pares)

        movimiento.metodo_valoracion = ServicioParametros.obtener("metodo_valoracion", METODO_PEPS)
        aplicar = _APLICADORES_POR_NATURALEZA[movimiento.naturaleza]
        total_cantidad, total_costo = aplicar(movimiento, movimiento.lineas_solicitadas)

        movimiento.estado = EstadoMovimiento.CONFIRMADO
        movimiento.total_cantidad = total_cantidad
        movimiento.total_costo = total_costo
        movimiento.aprobado_por = usuario
        movimiento.aprobado_en = timezone.now()
        movimiento.save()
        _evaluar_alertas_del_movimiento(movimiento)

        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "aprobar", "numero": movimiento.numero},
        )
        return movimiento

    @staticmethod
    @transaction.atomic
    def rechazar(movimiento: Movimiento, motivo: str, usuario) -> Movimiento:
        """
        Rechaza un movimiento pendiente sin tocar el inventario.

        :raises ValidationError: si el movimiento no está pendiente, o si no
            se da un motivo.
        """
        if movimiento.estado != EstadoMovimiento.PENDIENTE:
            raise ValidationError("Solo se puede rechazar un movimiento pendiente.")
        if not motivo.strip():
            raise ValidationError({"motivo": "Indique por qué se rechaza."})

        movimiento.estado = EstadoMovimiento.RECHAZADO
        movimiento.aprobado_por = usuario
        movimiento.aprobado_en = timezone.now()
        movimiento.observaciones = (
            f"{movimiento.observaciones}\nRechazado: {motivo.strip()}".strip()
        )
        movimiento.save()

        ServicioAuditoria.registrar(
            entidad="Movimiento", entidad_id=movimiento.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "rechazar", "numero": movimiento.numero,
                    "motivo": motivo.strip()},
        )
        return movimiento
