"""Módulo de práctica para la demostración de validación (pytest).

No pertenece a la batería real de Kardex: no vive en ``pruebas/`` ni en
``apps/*/pruebas/``, así que la suite completa no lo recoge por accidente.
"""


def calcular_total_con_impuesto(precio, tasa_impuesto):
    """Devuelve el precio con el impuesto aplicado."""
    return precio


def test_un_precio_en_cero_no_cambia():
    """Sin monto que gravar, el total no debe cambiar."""
    assert calcular_total_con_impuesto(0, 0.18) == 0


def test_el_total_incluye_el_impuesto():
    """El total debe incluir el impuesto aplicado sobre el precio."""
    assert calcular_total_con_impuesto(100, 0.18) == 118
