"""
Pruebas de la valoración de salidas: PEPS, UEPS y promedio ponderado.

Son pruebas de lógica pura — los «lotes» son instancias de ``Lote`` sin
guardar, así que no hace falta base de datos para probar el algoritmo.
"""

from __future__ import annotations

from decimal import Decimal

from apps.movimientos.models import Lote
from apps.movimientos.valoracion import (
    METODO_PEPS,
    METODO_PROMEDIO,
    METODO_UEPS,
    costo_total_del_plan,
    costo_unitario_promedio_del_plan,
    orden_de_consumo,
    planificar_consumo,
)


def _lote(cantidad: str, costo: str, dias_atras: int) -> Lote:
    """Construye un lote sin guardar, con la cantidad y el costo indicados."""
    from django.utils import timezone  # pylint: disable=import-outside-toplevel

    return Lote(
        cantidad_disponible=Decimal(cantidad), costo_unitario=Decimal(costo),
        recibido_en=timezone.now() - timezone.timedelta(days=dias_atras),
    )


def test_peps_consume_primero_el_lote_mas_antiguo():
    """El plan PEPS agota el lote más viejo antes de tocar el más nuevo."""
    viejo = _lote("10", "100", dias_atras=30)
    nuevo = _lote("10", "150", dias_atras=1)

    plan = planificar_consumo([viejo, nuevo], Decimal("15"), METODO_PEPS, Decimal("125"))

    assert len(plan) == 2
    assert plan[0].lote is viejo and plan[0].cantidad == Decimal("10")
    assert plan[0].costo_unitario == Decimal("100")
    assert plan[1].lote is nuevo and plan[1].cantidad == Decimal("5")
    assert plan[1].costo_unitario == Decimal("150")


def test_ueps_consume_primero_el_lote_mas_nuevo():
    """El orden de consumo de UEPS es el inverso de PEPS."""
    assert orden_de_consumo(METODO_UEPS) == "-recibido_en"
    assert orden_de_consumo(METODO_PEPS) == "recibido_en"
    assert orden_de_consumo(METODO_PROMEDIO) == "recibido_en"


def test_promedio_ponderado_agota_el_lote_mas_antiguo_pero_valora_al_promedio():
    """Promedio ponderado sigue el orden PEPS, pero cada tramo cuesta el promedio."""
    viejo = _lote("10", "100", dias_atras=30)
    nuevo = _lote("10", "150", dias_atras=1)

    plan = planificar_consumo([viejo, nuevo], Decimal("15"), METODO_PROMEDIO, Decimal("125"))

    assert plan[0].lote is viejo and plan[0].costo_unitario == Decimal("125")
    assert plan[1].lote is nuevo and plan[1].costo_unitario == Decimal("125")
    assert costo_total_del_plan(plan) == Decimal("15") * Decimal("125")


def test_lotes_insuficientes_dejan_un_tramo_sin_lote():
    """Si los lotes no alcanzan, el resto queda como un tramo sin lote, al costo promedio."""
    unico = _lote("5", "100", dias_atras=1)

    plan = planificar_consumo([unico], Decimal("8"), METODO_PEPS, Decimal("110"))

    assert len(plan) == 2
    assert plan[0].lote is unico and plan[0].cantidad == Decimal("5")
    assert plan[1].lote is None and plan[1].cantidad == Decimal("3")
    assert plan[1].costo_unitario == Decimal("110")


def test_sin_lotes_disponibles_todo_el_plan_es_sin_lote():
    """Sin lotes con saldo, toda la cantidad se valora al costo promedio."""
    plan = planificar_consumo([], Decimal("4"), METODO_PEPS, Decimal("200"))

    assert len(plan) == 1
    assert plan[0].lote is None
    assert plan[0].cantidad == Decimal("4")
    assert plan[0].costo_unitario == Decimal("200")


def test_costo_total_del_plan_suma_cada_tramo():
    """El costo total nunca es cantidad × promedio bajo PEPS: es la suma real de cada tramo."""
    barato = _lote("5", "10", dias_atras=10)
    caro = _lote("5", "20", dias_atras=1)

    plan = planificar_consumo([barato, caro], Decimal("10"), METODO_PEPS, Decimal("15"))

    # 5×10 + 5×20 = 150, no 10×15 = 150 por casualidad en este caso —
    # se comprueba con cantidades desiguales para no dejar pasar el error.
    plan_desigual = planificar_consumo([barato, caro], Decimal("7"), METODO_PEPS, Decimal("15"))
    assert costo_total_del_plan(plan_desigual) == Decimal("5") * Decimal("10") + Decimal("2") * Decimal("20")
    assert costo_total_del_plan(plan) == Decimal("150.0000")


def test_costo_unitario_promedio_del_plan_es_el_equivalente_del_tramo_mixto():
    """El costo unitario que se guarda en la línea es el equivalente de todo el plan."""
    barato = _lote("5", "10", dias_atras=10)
    caro = _lote("5", "20", dias_atras=1)

    plan = planificar_consumo([barato, caro], Decimal("10"), METODO_PEPS, Decimal("15"))

    esperado = (Decimal("5") * Decimal("10") + Decimal("5") * Decimal("20")) / Decimal("10")
    assert costo_unitario_promedio_del_plan(plan) == esperado.quantize(Decimal("0.0001"))


def test_costo_unitario_promedio_con_plan_vacio_es_cero():
    """Un plan sin tramos (cantidad cero) no revienta con una división entre cero."""
    assert costo_unitario_promedio_del_plan([]) == Decimal("0")
