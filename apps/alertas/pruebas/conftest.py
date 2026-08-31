"""Accesorios compartidos por las pruebas de Alertas."""

from __future__ import annotations

import pytest

from apps.catalogo.models import Articulo, UnidadMedida
from apps.catalogo.services import ServicioArticulos, ServicioCategorias
from apps.movimientos.models import Naturaleza, TipoMovimiento


@pytest.fixture
def unidad(db) -> UnidadMedida:
    """Una unidad de medida de prueba."""
    return UnidadMedida.objects.create(codigo="UD", nombre="Unidad")


@pytest.fixture
def categoria(db):
    """Una categoría raíz de prueba."""
    return ServicioCategorias.crear("FER", "Ferretería", "", None)


@pytest.fixture
def articulo(categoria, unidad) -> Articulo:
    """Un artículo de prueba, sin existencia todavía."""
    return ServicioArticulos.crear(
        nombre="Cemento gris", categoria=categoria, unidad=unidad, stock_minimo_defecto=10,
    )


@pytest.fixture
def tipo_entrada(db) -> TipoMovimiento:
    """Tipo de movimiento de entrada, sin exigencias especiales."""
    return TipoMovimiento.objects.create(
        codigo="COMPRA", nombre="Compra", naturaleza=Naturaleza.ENTRADA, prefijo_numeracion="ENT",
    )


@pytest.fixture
def tipo_salida(db) -> TipoMovimiento:
    """Tipo de movimiento de salida, sin exigencias especiales."""
    return TipoMovimiento.objects.create(
        codigo="VENTA", nombre="Venta", naturaleza=Naturaleza.SALIDA, prefijo_numeracion="SAL",
    )
