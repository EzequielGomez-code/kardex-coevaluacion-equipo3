"""
Pruebas de ``ServicioAprobaciones``: un movimiento pendiente no toca el
inventario hasta que se aprueba.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.movimientos.models import EstadoMovimiento, Existencia, Lote
from apps.movimientos.services import ServicioAprobaciones, ServicioMovimientos


@pytest.mark.django_db
def test_ajuste_pendiente_no_toca_el_inventario(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Mientras espera aprobación, no existen líneas, lotes ni existencia."""
    movimiento = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo físico",
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("6"), "signo": 1,
                "costo_unitario": Decimal("15")}],
    )
    assert movimiento.estado == EstadoMovimiento.PENDIENTE
    assert movimiento.lineas.count() == 0
    assert not Lote.objects.filter(articulo=articulo).exists()
    assert not Existencia.objects.filter(articulo=articulo, cantidad__gt=0).exists()
    assert len(movimiento.lineas_solicitadas) == 1


@pytest.mark.django_db
def test_aprobar_aplica_los_efectos(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Aprobar un movimiento pendiente recién ahí crea sus líneas y actualiza la existencia."""
    movimiento = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo físico",
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("6"), "signo": 1,
                "costo_unitario": Decimal("15")}],
    )

    aprobado = ServicioAprobaciones.aprobar(movimiento, usuario_administrador)

    assert aprobado.estado == EstadoMovimiento.CONFIRMADO
    assert aprobado.aprobado_por_id == usuario_administrador.pk
    assert aprobado.lineas.count() == 1
    existencia = Existencia.objects.get(articulo=articulo, almacen=almacen)
    assert existencia.cantidad == Decimal("6")


@pytest.mark.django_db
def test_rechazar_no_toca_el_inventario(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Rechazar un movimiento pendiente lo descarta sin aplicar ningún efecto."""
    movimiento = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo físico",
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("6"), "signo": 1}],
    )

    rechazado = ServicioAprobaciones.rechazar(movimiento, "No corresponde", usuario_administrador)

    assert rechazado.estado == EstadoMovimiento.RECHAZADO
    assert rechazado.lineas.count() == 0
    assert not Existencia.objects.filter(articulo=articulo, cantidad__gt=0).exists()


@pytest.mark.django_db
def test_no_se_puede_aprobar_un_movimiento_ya_confirmado(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Solo un movimiento pendiente se puede aprobar."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    with pytest.raises(ValidationError):
        ServicioAprobaciones.aprobar(movimiento, usuario_administrador)


@pytest.mark.django_db
def test_rechazar_sin_motivo_falla(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Rechazar exige explicar por qué."""
    movimiento = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo", lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
    )
    with pytest.raises(ValidationError):
        ServicioAprobaciones.rechazar(movimiento, "   ", usuario_administrador)


@pytest.mark.django_db
def test_pendientes_lista_solo_los_que_esperan(
    tipo_ajuste_con_aprobacion, tipo_entrada, almacen, articulo, usuario_administrador
):
    """La bandeja de aprobaciones no mezcla movimientos ya resueltos."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    pendiente = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo", lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
    )

    pendientes = list(ServicioAprobaciones.pendientes())
    assert pendientes == [pendiente]
