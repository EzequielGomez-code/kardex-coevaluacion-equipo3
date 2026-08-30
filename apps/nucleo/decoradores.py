"""
Decoradores de control de acceso.

Seguridad #4 del brief (OWASP A01 — Pérdida de control de acceso): el permiso
se comprueba en el servidor, en cada vista. Ocultar el botón en la plantilla es
comodidad visual; lo que manda es este decorador. Una petición directa a la URL
sin el permiso devuelve 403 y queda registrada en la auditoría.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def _no_autenticado(request: HttpRequest) -> HttpResponse:
    """Envía al formulario de acceso conservando la URL solicitada."""
    destino = reverse("nucleo:iniciar_sesion")
    return redirect(f"{destino}?siguiente={request.get_full_path()}")


def requiere_sesion(vista: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Exige que haya una sesión iniciada."""

    @wraps(vista)
    def envoltura(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return _no_autenticado(request)
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_permiso(*claves: str) -> Callable:
    """
    Exige que el usuario tenga al menos una de las claves de permiso indicadas.

    :param claves: claves de la forma ``modulo.accion``.
    :returns: decorador listo para envolver una vista.
    """

    def decorador(vista: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(vista)
        def envoltura(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not request.user.is_authenticated:
                return _no_autenticado(request)

            if not any(request.user.tiene_permiso(clave) for clave in claves):
                # Importación diferida: evita un ciclo entre servicios y decoradores.
                from apps.nucleo.models import RegistroAuditoria  # pylint: disable=import-outside-toplevel
                from apps.nucleo.services import ServicioAuditoria  # pylint: disable=import-outside-toplevel

                ServicioAuditoria.registrar(
                    entidad="Acceso",
                    entidad_id=request.path,
                    accion=RegistroAuditoria.Accion.ACCESO_DENEGADO,
                    detalle={"ruta": request.path, "permisos_exigidos": list(claves)},
                )
                raise PermissionDenied(
                    "Su rol no tiene permiso para esta operación."
                )
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
