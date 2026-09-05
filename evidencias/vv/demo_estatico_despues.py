"""Archivo de demostración para la Unidad 3 (V&V): analisis estatico en vivo.

Version corregida de demo_estatico_antes.py, aplicando las correcciones
que Pylint sugirio: se retiran los imports sin uso, la variable sin uso y
la clausula "except" desnuda se reemplaza por el tipo de excepcion real.
"""


def calcular_descuento(precio, porcentaje_descuento_aplicado_al_cliente_frecuente):
    """Aplica un descuento y devuelve el precio final."""
    try:
        return precio - (precio * porcentaje_descuento_aplicado_al_cliente_frecuente / 100)
    except TypeError:
        return precio
