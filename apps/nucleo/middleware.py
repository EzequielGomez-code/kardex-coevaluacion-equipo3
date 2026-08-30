"""
Middleware que deja el usuario y la IP de la petición al alcance de los
servicios, para que la auditoría pueda registrarlos sin arrastrar el objeto
``request`` por toda la capa de negocio.

Se usa ``contextvars`` y no una variable global para que dos peticiones
atendidas a la vez no se pisen los datos.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

_usuario_actual: contextvars.ContextVar = contextvars.ContextVar("usuario_actual", default=None)
_ip_actual: contextvars.ContextVar = contextvars.ContextVar("ip_actual", default=None)


def usuario_actual():
    """Devuelve el usuario autenticado de la petición en curso, o ``None``."""
    return _usuario_actual.get()


def ip_actual() -> str | None:
    """Devuelve la IP de la petición en curso, o ``None``."""
    return _ip_actual.get()


def ip_de_la_peticion(request: HttpRequest) -> str | None:
    """
    Extrae la IP del cliente teniendo en cuenta el proxy de Render.

    Se toma la primera dirección de ``X-Forwarded-For`` porque las siguientes
    las añaden los intermediarios.
    """
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class MiddlewareUsuarioActual:
    """Publica usuario e IP en el contexto durante el ciclo de la petición."""

    def __init__(self, obtener_respuesta: Callable[[HttpRequest], HttpResponse]) -> None:
        self.obtener_respuesta = obtener_respuesta

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Fija el contexto, atiende la petición y lo limpia al terminar."""
        usuario = getattr(request, "user", None)
        if usuario is not None and not usuario.is_authenticated:
            usuario = None

        ficha_usuario = _usuario_actual.set(usuario)
        ficha_ip = _ip_actual.set(ip_de_la_peticion(request))
        try:
            return self.obtener_respuesta(request)
        finally:
            _usuario_actual.reset(ficha_usuario)
            _ip_actual.reset(ficha_ip)
