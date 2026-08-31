"""Accesorios compartidos por las pruebas de Movimientos."""

from __future__ import annotations

import pytest

from apps.catalogo.models import Articulo, UnidadMedida
from apps.catalogo.services import ServicioArticulos, ServicioCategorias
from apps.movimientos.models import Naturaleza, TipoMovimiento
from apps.nucleo.models import Almacen


@pytest.fixture
def segundo_almacen(db) -> Almacen:
    """Un segundo almacén, para probar transferencias."""
    return Almacen.objects.create(codigo="ALM-02", nombre="Sucursal de prueba")


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
    return ServicioArticulos.crear(nombre="Cemento gris", categoria=categoria, unidad=unidad)


@pytest.fixture
def otro_articulo(categoria, unidad) -> Articulo:
    """Un segundo artículo de prueba."""
    return ServicioArticulos.crear(nombre="Varilla 3/8", categoria=categoria, unidad=unidad)


@pytest.fixture
def tipo_entrada(db) -> TipoMovimiento:
    """Tipo de movimiento de entrada, sin exigencias especiales."""
    return TipoMovimiento.objects.create(
        codigo="COMPRA", nombre="Compra", naturaleza=Naturaleza.ENTRADA,
        prefijo_numeracion="ENT",
    )


@pytest.fixture
def tipo_entrada_con_ncf(db) -> TipoMovimiento:
    """Tipo de entrada que exige comprobante fiscal."""
    return TipoMovimiento.objects.create(
        codigo="COMPRA-NCF", nombre="Compra con NCF", naturaleza=Naturaleza.ENTRADA,
        prefijo_numeracion="ENTF", exige_ncf=True,
    )


@pytest.fixture
def tipo_salida(db) -> TipoMovimiento:
    """Tipo de movimiento de salida, sin exigencias especiales."""
    return TipoMovimiento.objects.create(
        codigo="VENTA", nombre="Venta", naturaleza=Naturaleza.SALIDA, prefijo_numeracion="SAL",
    )


@pytest.fixture
def tipo_transferencia(db) -> TipoMovimiento:
    """Tipo de movimiento de transferencia entre almacenes."""
    return TipoMovimiento.objects.create(
        codigo="TRASLADO", nombre="Traslado", naturaleza=Naturaleza.TRANSFERENCIA,
        prefijo_numeracion="TRF",
    )


@pytest.fixture
def tipo_ajuste(db) -> TipoMovimiento:
    """Tipo de movimiento de ajuste, sin aprobación."""
    return TipoMovimiento.objects.create(
        codigo="AJUSTE", nombre="Ajuste de inventario", naturaleza=Naturaleza.AJUSTE,
        prefijo_numeracion="AJU",
    )


@pytest.fixture
def tipo_ajuste_con_aprobacion(db) -> TipoMovimiento:
    """Tipo de ajuste que exige aprobación antes de aplicarse."""
    return TipoMovimiento.objects.create(
        codigo="AJUSTE-SUP", nombre="Ajuste supervisado", naturaleza=Naturaleza.AJUSTE,
        prefijo_numeracion="AJS", exige_aprobacion=True,
    )
