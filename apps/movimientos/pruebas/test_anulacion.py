"""
Pruebas de ``ServicioMovimientos.anular``: reversión por contrapartida, nunca
por borrado.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.alertas.models import Alerta, EstadoAlerta, ReglaAlerta, TipoRegla
from apps.movimientos.models import EstadoMovimiento, Existencia, Lote
from apps.movimientos.services import ServicioMovimientos


@pytest.mark.django_db
def test_anular_entrada_intacta_deja_el_lote_en_cero(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Anular una entrada cuyo lote nunca se tocó restaura la existencia a cero."""
    entrada = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("40")}],
    )

    contrapartida = ServicioMovimientos.anular(entrada, "Error de digitación", usuario_administrador)

    entrada.refresh_from_db()
    assert entrada.estado == EstadoMovimiento.ANULADO
    assert entrada.anulado_en is not None
    assert contrapartida.anula_id == entrada.pk
    assert contrapartida.estado == EstadoMovimiento.CONFIRMADO

    lote = Lote.objects.get(articulo=articulo, almacen=almacen)
    assert lote.cantidad_disponible == Decimal("0")
    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("0")
    assert existencia.valor == Decimal("0.0000")


@pytest.mark.django_db
def test_anular_entrada_ya_consumida_falla(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """Si el lote de la entrada ya se consumió, la anulación se rechaza: toca un ajuste."""
    entrada = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("40")}],
    )
    ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("2")}],
    )

    with pytest.raises(ValidationError):
        ServicioMovimientos.anular(entrada, "Intento inválido", usuario_administrador)


@pytest.mark.django_db
def test_anular_salida_restaura_el_lote_consumido(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """Anular una salida devuelve la cantidad exacta al lote del que salió."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("40")}],
    )
    salida = ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("6")}],
    )

    ServicioMovimientos.anular(salida, "Devolución del cliente", usuario_administrador)

    lote = Lote.objects.get(articulo=articulo, almacen=almacen)
    assert lote.cantidad_disponible == Decimal("10")
    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("10")


@pytest.mark.django_db
def test_anular_salida_cierra_la_alerta_de_stock_bajo_que_dejo(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """Anular la salida que provocó la alerta debe resolverla, igual que reponer stock a mano."""
    ReglaAlerta.objects.create(nombre="Existencia baja", tipo=TipoRegla.STOCK_BAJO)
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("10")}],
    )
    salida = ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("8")}],
    )
    assert Alerta.objects.filter(articulo=articulo, almacen=almacen, estado=EstadoAlerta.ABIERTA).exists()

    ServicioMovimientos.anular(salida, "Devolución del cliente", usuario_administrador)

    alerta = Alerta.objects.get(articulo=articulo, almacen=almacen)
    assert alerta.estado == EstadoAlerta.RESUELTA


@pytest.mark.django_db
def test_no_se_puede_anular_dos_veces(tipo_entrada, almacen, articulo, usuario_administrador):
    """Un movimiento ya anulado no admite una segunda anulación."""
    entrada = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )
    ServicioMovimientos.anular(entrada, "Primera anulación", usuario_administrador)
    entrada.refresh_from_db()
    with pytest.raises(ValidationError):
        ServicioMovimientos.anular(entrada, "Segunda anulación", usuario_administrador)


@pytest.mark.django_db
def test_anular_sin_motivo_falla(tipo_entrada, almacen, articulo, usuario_administrador):
    """La anulación exige un motivo."""
    entrada = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )
    with pytest.raises(ValidationError):
        ServicioMovimientos.anular(entrada, "   ", usuario_administrador)


@pytest.mark.django_db
def test_no_se_puede_anular_un_movimiento_no_confirmado(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Un movimiento pendiente (no confirmado) no se puede anular."""
    pendiente = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo", lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
    )
    assert pendiente.estado == EstadoMovimiento.PENDIENTE
    with pytest.raises(ValidationError):
        ServicioMovimientos.anular(pendiente, "No debería poder", usuario_administrador)
