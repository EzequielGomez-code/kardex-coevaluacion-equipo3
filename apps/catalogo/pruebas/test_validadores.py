"""
Pruebas de los validadores dominicanos del catálogo.

Puro Python: no tocan la base de datos, así que corren en milisegundos.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.catalogo.validadores import (
    formatear_rnc,
    normalizar_rnc,
    validar_ean13,
    validar_rnc,
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("1-31-12345-6", "131123456"),
        ("001-1234567-8", "00112345678"),
        ("  123 456 789 ", "123456789"),
        ("", ""),
    ],
)
def test_normalizar_rnc(entrada, esperado):
    """Se quedan solo los dígitos, sin guiones ni espacios."""
    assert normalizar_rnc(entrada) == esperado


def test_rnc_de_9_digitos_valido_no_lanza():
    """Un RNC con dígito de control correcto, calculado con los pesos de la DGII, pasa."""
    # base 13138964 con pesos [7,9,8,6,5,4,3,2]: suma=249, 249%11=8, 11-8=3.
    validar_rnc("131389643")


def test_rnc_de_9_digitos_con_digito_de_control_incorrecto():
    """Cambiar el último dígito rompe el control y debe rechazarse."""
    with pytest.raises(ValidationError, match="dígito de control"):
        validar_rnc("131389644")


def test_cedula_de_11_digitos_solo_valida_longitud():
    """Una cédula (11 dígitos) se acepta sin verificar dígito de control."""
    validar_rnc("00112345678")


@pytest.mark.parametrize("valor", ["12345", "1234567890123", "abc"])
def test_longitud_invalida_se_rechaza(valor):
    """Ni 9 ni 11 dígitos: se rechaza antes de calcular nada."""
    with pytest.raises(ValidationError, match="9 dígitos"):
        validar_rnc(valor)


def test_formatear_rnc_de_9_digitos():
    """El formato de lectura de un RNC de persona jurídica."""
    assert formatear_rnc("131389643") == "1-31-38964-3"


def test_formatear_cedula_de_11_digitos():
    """El formato de lectura de una cédula."""
    assert formatear_rnc("00112345678") == "001-1234567-8"


def test_formatear_valor_con_longitud_rara_lo_devuelve_tal_cual():
    """Si no encaja en ningún formato conocido, se devuelve solo normalizado."""
    assert formatear_rnc("12345") == "12345"


def test_ean13_valido_no_lanza():
    """Un código de barras real con dígito de control correcto pasa."""
    validar_ean13("4006381333931")


def test_ean13_con_digito_de_control_incorrecto():
    """Cambiar el último dígito rompe el control."""
    with pytest.raises(ValidationError, match="no es válido"):
        validar_ean13("4006381333930")


def test_ean13_con_longitud_incorrecta():
    """Menos de 13 dígitos se rechaza antes de calcular el control."""
    with pytest.raises(ValidationError, match="13 dígitos"):
        validar_ean13("123")
