"""Archivo de demostración para la Unidad 3 (V&V): analisis estatico en vivo.

No pertenece a la aplicacion (no esta en apps/ ni config/, y nada lo importa).
Existe solo para mostrar, en vivo, como Pylint detecta problemas reales antes
de que el codigo se ejecute -- esa es la definicion practica de "verificacion".
"""

import os
import json


def calcular_descuento(precio, porcentaje_descuento_aplicado_al_cliente_frecuente):
    """Aplica un descuento y devuelve el precio final."""
    try:
        resultado = precio - (precio * porcentaje_descuento_aplicado_al_cliente_frecuente / 100)
        auditoria = "descuento aplicado"
        return resultado
    except:
        return precio
