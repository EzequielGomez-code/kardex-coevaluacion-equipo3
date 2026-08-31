"""Pruebas de ``registrar_transferencia`` y ``registrar_ajuste``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.movimientos.models import EstadoMovimiento, Existencia, Lote
from apps.movimientos.services import ServicioMovimientos


@pytest.mark.django_db
def test_transferencia_mueve_existencia_y_conserva_el_costo(
    tipo_entrada, tipo_transferencia, almacen, segundo_almacen, articulo, usuario_administrador
):
    """El lote que se crea en el destino conserva el costo del lote de origen."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("20"), "costo_unitario": Decimal("75")}],
    )

    ServicioMovimientos.registrar_transferencia(
        tipo=tipo_transferencia, almacen_origen=almacen, almacen_destino=segundo_almacen,
        usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("12")}],
    )

    existencia_origen = Existencia.objects.get(articulo=articulo, almacen=almacen)
    existencia_destino = Existencia.objects.get(articulo=articulo, almacen=segundo_almacen)
    assert existencia_origen.cantidad == Decimal("8")
    assert existencia_destino.cantidad == Decimal("12")

    lote_destino = Lote.objects.get(articulo=articulo, almacen=segundo_almacen)
    assert lote_destino.costo_unitario == Decimal("75")
    assert lote_destino.cantidad_disponible == Decimal("12")


@pytest.mark.django_db
def test_transferencia_crea_un_lote_por_cada_costo_de_origen(
    tipo_entrada, tipo_transferencia, almacen, segundo_almacen, articulo, usuario_administrador
):
    """Si el origen tenía dos costos distintos, el destino recibe dos lotes."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("50")}],
    )
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("90")}],
    )

    ServicioMovimientos.registrar_transferencia(
        tipo=tipo_transferencia, almacen_origen=almacen, almacen_destino=segundo_almacen,
        usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("15")}],
    )

    lotes_destino = Lote.objects.filter(articulo=articulo, almacen=segundo_almacen).order_by("costo_unitario")
    assert list(lotes_destino.values_list("costo_unitario", "cantidad_disponible")) == [
        (Decimal("50"), Decimal("10")), (Decimal("90"), Decimal("5")),
    ]


@pytest.mark.django_db
def test_transferencia_al_mismo_almacen_falla(
    tipo_transferencia, almacen, articulo, usuario_administrador
):
    """Origen y destino no pueden ser el mismo almacén."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_transferencia(
            tipo=tipo_transferencia, almacen_origen=almacen, almacen_destino=almacen,
            usuario=usuario_administrador,
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1")}],
        )


@pytest.mark.django_db
def test_ajuste_positivo_crea_lote_al_costo_indicado(
    tipo_ajuste, almacen, articulo, usuario_administrador
):
    """Un ajuste que encuentra existencia crea un lote, igual que una entrada."""
    movimiento = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste, almacen=almacen, usuario=usuario_administrador, motivo="Conteo físico",
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("4"), "signo": 1,
                "costo_unitario": Decimal("30")}],
    )
    assert movimiento.estado == EstadoMovimiento.CONFIRMADO
    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("4")
    assert Lote.objects.filter(articulo=articulo, almacen=almacen).exists()


@pytest.mark.django_db
def test_ajuste_negativo_consume_lotes_como_una_salida(
    tipo_entrada, tipo_ajuste, almacen, articulo, usuario_administrador
):
    """Un ajuste que da de baja existencia consume lotes por PEPS, igual que una salida."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("20")}],
    )
    ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste, almacen=almacen, usuario=usuario_administrador, motivo="Merma detectada",
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "signo": -1}],
    )
    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("7")


@pytest.mark.django_db
def test_ajuste_sin_motivo_falla(tipo_ajuste, almacen, articulo, usuario_administrador):
    """Todo ajuste exige un motivo, sin excepción."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_ajuste(
            tipo=tipo_ajuste, almacen=almacen, usuario=usuario_administrador, motivo="   ",
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
        )


@pytest.mark.django_db
def test_ajuste_con_tipo_de_otra_naturaleza_falla(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """No se puede registrar un ajuste con un tipo que no sea de naturaleza «ajuste»."""
    with pytest.raises(ValidationError):
        ServicioMovimientos.registrar_ajuste(
            tipo=tipo_entrada, almacen=almacen, usuario=usuario_administrador, motivo="Motivo",
            lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
        )
