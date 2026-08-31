"""
Validadores propios del catálogo dominicano.

El Registro Nacional de Contribuyente (RNC) tiene 9 dígitos para personas
jurídicas y 11 para personas físicas (en cuyo caso coincide con la cédula).
Se guarda normalizado (solo dígitos) y se muestra formateado.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

# Pesos del dígito verificador del RNC de 9 dígitos (persona jurídica),
# según el algoritmo módulo 11 publicado por la DGII.
_PESOS_RNC_9 = [7, 9, 8, 6, 5, 4, 3, 2]


def normalizar_rnc(valor: str) -> str:
    """Deja solo los dígitos de un RNC o cédula, sin guiones ni espacios."""
    return re.sub(r"\D", "", valor or "")


def validar_rnc(valor: str) -> None:
    """
    Comprueba que un RNC o cédula tenga una forma válida.

    Un RNC de persona jurídica (9 dígitos) verifica su dígito de control con
    el algoritmo módulo 11 de la DGII. Una cédula (11 dígitos) solo se
    comprueba en longitud: validar su dígito de control exige un algoritmo
    distinto, fuera del alcance de este catálogo.

    :raises ValidationError: si el valor no tiene una forma válida.
    """
    digitos = normalizar_rnc(valor)

    if len(digitos) == 11:
        return  # cédula: solo se exige la longitud

    if len(digitos) != 9:
        raise ValidationError("El RNC debe tener 9 dígitos, o 11 si es una cédula.")

    suma = sum(
        int(digito) * peso for digito, peso in zip(digitos[:8], _PESOS_RNC_9, strict=True)
    )
    resto = suma % 11
    verificador_esperado = 11 - resto
    if verificador_esperado == 11:
        verificador_esperado = 2
    elif verificador_esperado == 10:
        verificador_esperado = 1

    if int(digitos[8]) != verificador_esperado:
        raise ValidationError("El RNC no es válido: el dígito de control no coincide.")


def formatear_rnc(valor: str) -> str:
    """Devuelve un RNC o cédula en su formato de lectura: ``1-31-12345-6``."""
    digitos = normalizar_rnc(valor)
    if len(digitos) == 9:
        return f"{digitos[0]}-{digitos[1:3]}-{digitos[3:8]}-{digitos[8]}"
    if len(digitos) == 11:
        return f"{digitos[0:3]}-{digitos[3:10]}-{digitos[10]}"
    return digitos


def validar_ean13(valor: str) -> None:
    """
    Comprueba el dígito de control de un código de barras EAN-13.

    :raises ValidationError: si el valor no tiene 13 dígitos o el dígito de
        control no coincide.
    """
    digitos = normalizar_rnc(valor)
    if len(digitos) != 13:
        raise ValidationError("El código de barras EAN-13 debe tener 13 dígitos.")

    suma = sum(
        int(digito) * (1 if posicion % 2 == 0 else 3)
        for posicion, digito in enumerate(digitos[:12])
    )
    verificador_esperado = (10 - (suma % 10)) % 10

    if int(digitos[12]) != verificador_esperado:
        raise ValidationError("El código de barras no es válido: el dígito de control no coincide.")
