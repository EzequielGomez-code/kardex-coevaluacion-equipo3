"""Prueba de demostración para la Unidad 3 (V&V): validación en vivo.

No pertenece a la batería real de Kardex (no vive en ``pruebas/`` ni en
``apps/*/pruebas/``, así que pytest no la recoge por accidente al correr
la suite completa). Existe solo para mostrar, en vivo, que pytest sí
detecta cuando el comportamiento no coincide con lo esperado -- esa es la
definición práctica de "validación": hay que ejecutar el código para
descubrirlo, ningún análisis estático como Pylint lo puede ver.
"""


def calcular_total_con_impuesto(precio, tasa_impuesto):
    """Devuelve el precio con el impuesto aplicado."""
    return precio + (precio * tasa_impuesto)


def test_el_total_incluye_el_impuesto():
    """Caso correcto: 100 con 18% de impuesto debe dar 118."""
    assert calcular_total_con_impuesto(100, 0.18) == 118


def test_demo_de_una_validacion_que_falla():
    """Se deja fallar a propósito para la demostración en vivo.

    Afirma un resultado que la función no produce, para que el reporte de
    pytest lo marque en rojo delante de la clase.
    """
    assert calcular_total_con_impuesto(100, 0.18) == 100
