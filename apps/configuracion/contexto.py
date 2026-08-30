"""
Procesador de contexto que publica los parámetros del sistema en todas las
plantillas.

Gracias a esto, ``{{ parametros.moneda }}`` funciona en cualquier plantilla y
un cambio en la pantalla de parámetros se ve de inmediato, sin reiniciar el
servidor (criterio 9.6 del brief).
"""

from __future__ import annotations

import logging

from django.db import DatabaseError, OperationalError, ProgrammingError
from django.http import HttpRequest

from apps.configuracion.services import ServicioParametros

registro = logging.getLogger("kardex.configuracion")


def parametros_del_sistema(request: HttpRequest) -> dict:  # pylint: disable=unused-argument
    """Devuelve ``{"parametros": {clave: valor}}`` para las plantillas."""
    try:
        return {"parametros": ServicioParametros.todos()}
    except (OperationalError, ProgrammingError, DatabaseError):
        # Ocurre antes de la primera migración; no debe impedir que cargue la página.
        registro.debug("Parámetros no disponibles todavía (¿faltan migraciones?).")
        return {"parametros": {}}
