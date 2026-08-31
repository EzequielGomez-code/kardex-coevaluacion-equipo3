"""
Valoración de salidas: qué lotes se consumen y a qué costo.

Lógica de dominio pura, sin tocar el ORM, para poder probarla de forma
exhaustiva sin fixtures de base de datos. Quien llama (``ServicioMovimientos``)
es responsable de bloquear las filas con ``select_for_update`` y de aplicar el
plan que esta función calcula.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.movimientos.models import Lote

METODO_PEPS = "PEPS"
METODO_UEPS = "UEPS"
METODO_PROMEDIO = "Promedio ponderado"

CUATRO_DECIMALES = Decimal("0.0001")


@dataclass(frozen=True)
class ItemDeConsumo:
    """Un tramo del plan: cuánto sale de qué lote (o sin lote) y a qué costo."""

    lote: Lote | None
    cantidad: Decimal
    costo_unitario: Decimal

    @property
    def costo_total(self) -> Decimal:
        """Costo de este tramo, redondeado a cuatro decimales."""
        return (self.cantidad * self.costo_unitario).quantize(CUATRO_DECIMALES)


def orden_de_consumo(metodo: str) -> str:
    """
    Campo de ordenamiento con el que se recorren los lotes disponibles.

    PEPS y Promedio ponderado agotan primero el lote más antiguo — la única
    diferencia entre ambos es a qué costo se valora cada tramo, no qué lote
    se agota primero (ver :func:`planificar_consumo`). UEPS invierte el orden.
    """
    return "-recibido_en" if metodo == METODO_UEPS else "recibido_en"


def planificar_consumo(
    lotes_disponibles: Iterable[Lote],
    cantidad: Decimal,
    metodo: str,
    costo_promedio_actual: Decimal,
) -> list[ItemDeConsumo]:
    """
    Reparte ``cantidad`` entre los lotes disponibles.

    ``lotes_disponibles`` debe llegar ya bloqueado y ordenado según
    :func:`orden_de_consumo`. Si los lotes no alcanzan, el resto queda como
    un tramo sin lote (``lote=None``), valorado al costo promedio actual —
    el servicio decide si ese tramo es aceptable según
    ``permitir_stock_negativo``.
    """
    pendiente = cantidad
    plan: list[ItemDeConsumo] = []
    for lote in lotes_disponibles:
        if pendiente <= 0:
            break
        tomar = min(lote.cantidad_disponible, pendiente)
        if tomar <= 0:
            continue
        costo = costo_promedio_actual if metodo == METODO_PROMEDIO else lote.costo_unitario
        plan.append(ItemDeConsumo(lote=lote, cantidad=tomar, costo_unitario=costo))
        pendiente -= tomar

    if pendiente > 0:
        plan.append(
            ItemDeConsumo(lote=None, cantidad=pendiente, costo_unitario=costo_promedio_actual)
        )
    return plan


def costo_total_del_plan(plan: list[ItemDeConsumo]) -> Decimal:
    """Suma de los costos de cada tramo del plan."""
    return sum((item.costo_total for item in plan), Decimal("0")).quantize(CUATRO_DECIMALES)


def costo_unitario_promedio_del_plan(plan: list[ItemDeConsumo]) -> Decimal:
    """Costo unitario equivalente de todo el plan, para mostrar en la línea."""
    cantidad_total = sum((item.cantidad for item in plan), Decimal("0"))
    if not cantidad_total:
        return Decimal("0")
    return (costo_total_del_plan(plan) / cantidad_total).quantize(CUATRO_DECIMALES)
