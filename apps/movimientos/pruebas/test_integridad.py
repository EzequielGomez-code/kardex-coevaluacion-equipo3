"""
Pruebas de integridad del libro mayor: ``MovimientoLinea`` no se edita ni se
borra una vez creada, y ``anular`` deja la bandeja de alertas al día.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.movimientos.models import MovimientoLinea
from apps.movimientos.services import ServicioAprobaciones, ServicioMovimientos


@pytest.mark.django_db
def test_no_se_puede_editar_una_linea_ya_creada(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Una línea de movimiento es libro mayor: reescribirla debe fallar siempre."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )
    linea = movimiento.lineas.get()
    linea.cantidad = Decimal("999")
    with pytest.raises(ValueError):
        linea.save()


@pytest.mark.django_db
def test_no_se_puede_borrar_una_linea_directamente(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Borrar una línea fuera de la cascada del movimiento debe fallar siempre."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10")}],
    )
    linea = movimiento.lineas.get()
    with pytest.raises(ValueError):
        linea.delete()
    assert MovimientoLinea.objects.filter(pk=linea.pk).exists()


@pytest.mark.django_db
def test_no_se_puede_reescribir_un_movimiento_rechazado(
    tipo_ajuste_con_aprobacion, almacen, articulo, usuario_administrador
):
    """Un movimiento rechazado es tan terminal como uno anulado: no se vuelve a escribir."""
    pendiente = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo", lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
    )
    rechazado = ServicioAprobaciones.rechazar(pendiente, "No corresponde", usuario_administrador)
    rechazado.observaciones = "Intento de reescritura"
    with pytest.raises(ValueError):
        rechazado.save()
