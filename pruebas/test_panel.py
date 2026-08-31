"""
Prueba del gráfico de existencias del panel: sus coordenadas son SVG, no
texto para leer, así que no pueden pasar por el formato regional del sitio.
"""

from __future__ import annotations

import pytest
from django.shortcuts import render


@pytest.mark.django_db
def test_el_ancho_de_las_barras_no_lleva_coma_decimal(rf, usuario_administrador):
    """
    En español (``es-do``) Django escribe los números con coma decimal — 94.8
    se muestra «94,8». Esa coma es perfecta en una celda de tabla y rompe por
    completo un atributo ``width`` de SVG, que exige punto. El gráfico usa
    ``|unlocalize`` a propósito para evitarlo.
    """
    peticion = rf.get("/")
    peticion.user = usuario_administrador
    contexto = {
        "titulo": "Panel",
        "grafico_existencias": {
            "alto_total": 40,
            "barras": [
                {"codigo": "ALM-01", "valor": "1000.00", "y": 0, "ancho": 94.8},
                {"codigo": "ALM-02", "valor": "500.00", "y": 40, "ancho": 32.1},
            ],
        },
    }
    respuesta = render(peticion, "nucleo/panel.html", contexto)
    salida = respuesta.content.decode()

    assert "94,8" not in salida
    assert "32,1" not in salida
    assert 'width="94.8"' in salida
    assert 'width="32.1"' in salida
