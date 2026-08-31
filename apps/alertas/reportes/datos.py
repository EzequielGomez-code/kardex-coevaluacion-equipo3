"""
Datos listos para exportar.

Cada función devuelve ``(encabezados, filas)`` ya formateados como texto —
fechas en dd/mm/aaaa, cantidades y montos con punto fijo — así ``pdf.py`` y
``excel.py`` solo se ocupan de la presentación, nunca de convertir un tipo.
"""

from __future__ import annotations

from apps.movimientos.repositories import (
    RepositorioExistencias,
    RepositorioKardex,
    RepositorioMovimientos,
)


def _cantidad(valor) -> str:
    return f"{valor:,.4f}"


def _moneda(valor) -> str:
    return f"{valor:,.2f}"


def existencias(busqueda: str = "", almacen_id: int | None = None) -> tuple[list[str], list[list[str]]]:
    """Existencias actuales, con su costo promedio y valor."""
    encabezados = ["SKU", "Artículo", "Almacén", "Cantidad", "Costo promedio", "Valor", "Mínimo"]
    filas = [
        [
            fila.articulo.sku, fila.articulo.nombre, fila.almacen.codigo,
            _cantidad(fila.cantidad), _moneda(fila.costo_promedio), _moneda(fila.valor),
            _cantidad(fila.stock_minimo),
        ]
        for fila in RepositorioExistencias.listar(busqueda=busqueda, almacen_id=almacen_id)
    ]
    return encabezados, filas


def valorizacion() -> tuple[list[str], list[list[str]]]:
    """Valor del inventario agrupado por almacén."""
    encabezados = ["Almacén", "Valor total"]
    filas = [
        [fila["almacen__nombre"], _moneda(fila["total"])]
        for fila in RepositorioExistencias.valor_por_almacen()
    ]
    return encabezados, filas


def movimientos_por_rango(
    desde=None, hasta=None, tipo_id: int | None = None, almacen_id: int | None = None,
) -> tuple[list[str], list[list[str]]]:
    """Movimientos confirmados dentro de un rango de fechas."""
    encabezados = ["Número", "Tipo", "Fecha", "Almacén", "Cantidad", "Costo", "Estado"]
    filas = []
    for movimiento in RepositorioMovimientos.listar(
        tipo_id=tipo_id, almacen_id=almacen_id, desde=desde, hasta=hasta
    ):
        almacen = movimiento.almacen_destino or movimiento.almacen_origen
        filas.append(
            [
                movimiento.numero, movimiento.tipo.nombre, movimiento.fecha.strftime("%d/%m/%Y %H:%M"),
                almacen.codigo if almacen else "—", _cantidad(movimiento.total_cantidad),
                _moneda(movimiento.total_costo), movimiento.get_estado_display(),
            ]
        )
    return encabezados, filas


def kardex_de_articulo(
    articulo_id: int, almacen_id: int | None = None,
) -> tuple[list[str], list[list[str]]]:
    """Historial cronológico de un artículo, con su saldo corrido."""
    encabezados = ["Fecha", "Movimiento", "Tipo", "Almacén", "Cantidad", "Costo unitario", "Saldo"]
    filas = []
    for linea in RepositorioKardex.lineas_de(articulo_id, almacen_id):
        signo = "+" if linea.signo > 0 else "-"
        filas.append(
            [
                linea.movimiento.fecha.strftime("%d/%m/%Y %H:%M"), linea.movimiento.numero,
                linea.movimiento.tipo.nombre, linea.almacen.codigo,
                f"{signo}{_cantidad(linea.cantidad)}", _moneda(linea.costo_unitario),
                _cantidad(linea.saldo_posterior),
            ]
        )
    return encabezados, filas
