"""
Pruebas de ``ServicioEvaluador``: idempotencia, apertura y cierre automático
de alertas.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.alertas.models import Alerta, EstadoAlerta, ReglaAlerta, TipoRegla
from apps.alertas.services import ServicioEvaluador
from apps.movimientos.services import ServicioMovimientos
from apps.nucleo.models import Almacen


@pytest.fixture
def regla_stock_bajo(db) -> ReglaAlerta:
    """Regla de existencia bajo mínimo, sin restricción de almacén ni categoría."""
    return ReglaAlerta.objects.create(nombre="Existencia baja", tipo=TipoRegla.STOCK_BAJO)


@pytest.fixture
def regla_stock_cero(db) -> ReglaAlerta:
    """Regla de existencia en cero."""
    return ReglaAlerta.objects.create(nombre="Sin existencia", tipo=TipoRegla.STOCK_CERO)


@pytest.mark.django_db
def test_entrada_insuficiente_abre_alerta_de_stock_bajo(
    regla_stock_bajo, tipo_entrada, almacen, articulo, usuario_administrador
):
    """Una entrada que deja la existencia bajo el mínimo abre una alerta."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    alerta = Alerta.objects.get(regla=regla_stock_bajo, articulo=articulo, almacen=almacen)
    assert alerta.estado == EstadoAlerta.ABIERTA
    assert "3" in alerta.mensaje


@pytest.mark.django_db
def test_entrada_suficiente_no_abre_alerta(
    regla_stock_bajo, tipo_entrada, almacen, articulo, usuario_administrador
):
    """Si la existencia queda por encima del mínimo, no se genera ninguna alerta."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("50"), "costo_unitario": Decimal("10")}],
    )
    assert not Alerta.objects.filter(regla=regla_stock_bajo).exists()


@pytest.mark.django_db
def test_reponer_stock_cierra_la_alerta_automaticamente(
    regla_stock_bajo, tipo_entrada, almacen, articulo, usuario_administrador
):
    """Cuando la existencia vuelve a estar por encima del mínimo, la alerta se resuelve sola."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    assert Alerta.objects.filter(regla=regla_stock_bajo, estado=EstadoAlerta.ABIERTA).exists()

    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("50"), "costo_unitario": Decimal("10")}],
    )
    alerta = Alerta.objects.get(regla=regla_stock_bajo, articulo=articulo, almacen=almacen)
    assert alerta.estado == EstadoAlerta.RESUELTA


@pytest.mark.django_db
def test_evaluador_no_duplica_la_misma_alerta_abierta(
    regla_stock_bajo, tipo_entrada, almacen, articulo, usuario_administrador
):
    """Evaluar dos veces la misma condición no crea una segunda alerta."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    ServicioEvaluador.evaluar_pares([(articulo.pk, almacen.pk)])
    ServicioEvaluador.evaluar_todo()
    assert Alerta.objects.filter(regla=regla_stock_bajo).count() == 1


@pytest.mark.django_db
def test_stock_cero_y_stock_bajo_son_mutuamente_excluyentes(
    regla_stock_bajo, regla_stock_cero, tipo_entrada, tipo_salida, almacen, articulo,
    usuario_administrador,
):
    """Al vaciarse la existencia, la alerta de stock bajo se resuelve y se abre la de stock cero."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    assert Alerta.objects.filter(regla=regla_stock_bajo, estado=EstadoAlerta.ABIERTA).exists()

    ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3")}],
    )
    alerta_bajo = Alerta.objects.get(regla=regla_stock_bajo, articulo=articulo, almacen=almacen)
    alerta_cero = Alerta.objects.get(regla=regla_stock_cero, articulo=articulo, almacen=almacen)
    assert alerta_bajo.estado == EstadoAlerta.RESUELTA
    assert alerta_cero.estado == EstadoAlerta.ABIERTA


@pytest.mark.django_db
def test_regla_limitada_a_un_almacen_no_aplica_a_otro(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Una regla restringida a un almacén no genera alertas en los demás."""
    otro_almacen = Almacen.objects.create(codigo="ALM-77", nombre="Otro almacén")
    regla = ReglaAlerta.objects.create(nombre="Solo ALM-99", tipo=TipoRegla.STOCK_BAJO)
    regla.almacenes.add(otro_almacen)

    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    assert not Alerta.objects.filter(regla=regla).exists()


@pytest.mark.django_db
def test_evaluar_todo_recorre_reglas_inactivas_sin_generar_alertas(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Una regla inactiva no genera alertas aunque la condición se cumpla."""
    regla = ReglaAlerta.objects.create(
        nombre="Inactiva", tipo=TipoRegla.STOCK_BAJO, activa=False,
    )
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    assert not Alerta.objects.filter(regla=regla).exists()


@pytest.mark.django_db
def test_regla_de_vencimiento_respeta_el_almacen_de_la_regla(
    tipo_entrada, almacen, articulo, usuario_administrador
):
    """Un lote por vencer en un almacén no debe disparar una regla limitada a otro."""
    otro_almacen = Almacen.objects.create(codigo="ALM-88", nombre="Otro almacén")
    regla = ReglaAlerta.objects.create(
        nombre="Vence pronto", tipo=TipoRegla.VENCIMIENTO_PROXIMO, dias_umbral=30,
    )
    regla.almacenes.add(otro_almacen)

    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{
            "articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10"),
            "fecha_vencimiento": timezone.localdate() + timedelta(days=5),
        }],
    )
    ServicioEvaluador.evaluar_todo()
    assert not Alerta.objects.filter(regla=regla).exists()


@pytest.mark.django_db
def test_regla_de_vencimiento_se_cierra_sola_cuando_el_lote_se_agota(
    tipo_entrada, tipo_salida, almacen, articulo, usuario_administrador
):
    """Consumir por completo el lote que disparó la alerta la resuelve en la siguiente pasada."""
    regla = ReglaAlerta.objects.create(
        nombre="Vence pronto", tipo=TipoRegla.VENCIMIENTO_PROXIMO, dias_umbral=30,
    )
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{
            "articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("10"),
            "fecha_vencimiento": timezone.localdate() + timedelta(days=5),
        }],
    )
    ServicioEvaluador.evaluar_todo()
    assert Alerta.objects.filter(regla=regla, estado=EstadoAlerta.ABIERTA).exists()

    ServicioMovimientos.registrar_salida(
        tipo=tipo_salida, almacen_origen=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5")}],
    )
    ServicioEvaluador.evaluar_todo()
    alerta = Alerta.objects.get(regla=regla, articulo=articulo, almacen=almacen)
    assert alerta.estado == EstadoAlerta.RESUELTA


@pytest.mark.django_db
def test_evaluar_todo_no_consulta_una_vez_por_par(
    regla_stock_bajo, regla_stock_cero, tipo_entrada, almacen, articulo,
    usuario_administrador, django_assert_max_num_queries,
):
    """
    El evaluador decide en memoria y escribe en bloque.

    Antes preguntaba a la base si ya había alerta abierta **por cada par**
    (artículo, almacén) y por cada regla, así que el costo crecía con el
    tamaño del inventario: con la base en otra región, «Evaluar ahora»
    superaba el tiempo límite del servidor. Esta prueba fija ese contrato —
    el conteo no debe depender de cuántas existencias haya.
    """
    segundo_almacen = Almacen.objects.create(codigo="ALM-98", nombre="Segundo depósito")
    for destino in (almacen, segundo_almacen):
        ServicioMovimientos.registrar_entrada(
            tipo=tipo_entrada, almacen_destino=destino, usuario=usuario_administrador,
            lineas=[{
                "articulo_id": articulo.pk, "cantidad": Decimal("3"),
                "costo_unitario": Decimal("10"),
            }],
        )

    # Dos almacenes × dos reglas = cuatro pares evaluados. Con el defecto
    # anterior esto solo bajaba de veinte consultas por casualidad.
    with django_assert_max_num_queries(12):
        ServicioEvaluador.evaluar_todo()

    assert Alerta.objects.filter(estado=EstadoAlerta.ABIERTA).count() == 2
