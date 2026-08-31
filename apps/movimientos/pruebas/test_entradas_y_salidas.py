"""
Pruebas de ``ServicioMovimientos.registrar_entrada`` y ``registrar_salida``.

El caso central del brief: una salida debe consumir primero el lote más
antiguo, y la existencia nunca debe quedar negativa sin autorización expresa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.movimientos.models import EstadoMovimiento, Existencia, Lote, MovimientoLinea
from apps.movimientos.services import ServicioMovimientos


@pytest.mark.django_db
def test_registrar_entrada_crea_lote_y_existencia(tipo_entrada, almacen, articulo, usuario_administrador):
    """Una entrada confirmada crea su lote y actualiza la existencia del almacén."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("100"), "costo_unitario": Decimal("50")}],
    )

    assert movimiento.estado == EstadoMovimiento.CONFIRMADO
    assert movimiento.total_cantidad == Decimal("100")
    assert movimiento.total_costo == Decimal("5000.0000")

    lote = Lote.objects.get(articulo=articulo, almacen=almacen)
    assert lote.cantidad_disponible == Decimal("100")
    assert lote.cantidad_inicial == Decimal("100")

    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("100")
    assert existencia.valor == Decimal("5000.0000")


@pytest.mark.django_db
def test_entrada_con_tipo_de_otra_naturaleza_falla(tipo_salida, almacen, articulo, usuario_administrador):
    """No se puede registrar una entrada con un tipo configurado como salida."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_entrada(
            tipo=tipo_salida, almacen_destino=almacen, usuario=usuario_administrador,
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
        )


@pytest.mark.django_db
def test_entrada_sin_lineas_falla(tipo_entrada, almacen, usuario_administrador):
    """Una entrada sin líneas no se registra."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_entrada(
            tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador, lineas=[],
        )


@pytest.mark.django_db
def test_entrada_exige_ncf_cuando_el_tipo_lo_pide(
    tipo_entrada_con_ncf, almacen, articulo, usuario_administrador
):
    """Un tipo con ``exige_ncf`` rechaza una entrada sin comprobante fiscal."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_entrada(
            tipo=tipo_entrada_con_ncf, almacen_destino=almacen, usuario=usuario_administrador,
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
        )


@pytest.mark.django_db
def test_ncf_repetido_con_el_mismo_proveedor_falla(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """El mismo NCF no se puede registrar dos veces para el mismo proveedor."""
    from apps.catalogo.services import ServicioProveedores  # pylint: disable=import-outside-toplevel

    proveedor = ServicioProveedores.crear(codigo="PROV1", razon_social="Suplidora Uno")
    datos = {
        "tipo": tipo_entrada, "almacen_destino": almacen, "usuario": usuario_administrador,
        "proveedor": proveedor, "ncf": "B0100000001",
        "lineas": [{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    }
    ServicioMovimientos.registrar_entrada(**datos)
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_entrada(**datos)


@pytest.mark.django_db
def test_salida_consume_primero_el_lote_mas_antiguo(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """
    Criterio del brief §10: dos entradas a costos distintos, una salida
    parcial, y el kardex debe mostrar que se consumió primero el lote viejo.
    """
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("100")}],
    )
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("150")}],
    )

    salida = ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("15")}],
    )

    lote_viejo = Lote.objects.get(costo_unitario=Decimal("100"))
    lote_nuevo = Lote.objects.get(costo_unitario=Decimal("150"))
    assert lote_viejo.cantidad_disponible == Decimal("0")
    assert lote_nuevo.cantidad_disponible == Decimal("5")

    linea_salida = salida.lineas.get(signo=-1)
    assert linea_salida.costo_total == Decimal("10") * Decimal("100") + Decimal("5") * Decimal("150")

    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("5")


@pytest.mark.django_db
def test_salida_sin_existencia_suficiente_falla_por_defecto(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """Sin el parámetro ``permitir_stock_negativo``, la salida se rechaza."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_salida(
            tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10")}],
        )


@pytest.mark.django_db
def test_salida_con_stock_negativo_permitido_deja_tramo_sin_lote(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador, parametros_basicos
):
    """Con el parámetro activado, la salida se acepta y el resto queda sin lote."""
    from apps.configuracion.models import Parametro  # pylint: disable=import-outside-toplevel

    Parametro.objects.filter(clave="permitir_stock_negativo").update(valor="true")
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )

    salida = ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("8")}],
    )

    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("-3")
    linea = salida.lineas.get(signo=-1)
    assert linea.consumos.filter(lote__isnull=True).exists()


@pytest.mark.django_db
def test_movimiento_confirmado_no_se_puede_editar(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Un movimiento confirmado rechaza cualquier intento de reescritura fuera de la anulación."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    movimiento.motivo = "Intento de edición"
    with pytest.raises(ValueError):
        movimiento.save()


@pytest.mark.django_db
def test_linea_de_movimiento_registra_saldo_posterior_correcto(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """El saldo corrido de cada línea refleja la existencia justo después de aplicarse."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("20"), "costo_unitario": Decimal("5")}],
    )
    ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("7")}],
    )

    saldos = list(
        MovimientoLinea.objects.filter(articulo=articulo).order_by("id").values_list(
            "saldo_posterior", flat=True
        )
    )
    assert saldos == [Decimal("20.0000"), Decimal("13.0000")]
