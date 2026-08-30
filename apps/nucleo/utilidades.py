"""
Utilidades compartidas por las vistas de todas las apps.

Paginación con el texto «Mostrando 1–25 de 340» que pide el punto 5.4, y las
respuestas HTMX que disparan el toast y la recarga de la tabla.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Page, Paginator
from django.http import HttpRequest, HttpResponse

POR_PAGINA_POR_OMISION = 25


def paginar(request: HttpRequest, consulta: Any,
            por_pagina: int = POR_PAGINA_POR_OMISION) -> dict:
    """
    Pagina un conjunto de resultados y arma los datos que usa ``paginacion.html``.

    :param request: petición en curso; se lee ``?pagina=`` de la URL.
    :param consulta: cualquier iterable o ``QuerySet``.
    :param por_pagina: cantidad de filas por página.
    :returns: diccionario con la página, el rango mostrado y el total.
    """
    paginador = Paginator(consulta, por_pagina)
    numero = request.GET.get("pagina", "1")
    try:
        pagina: Page = paginador.page(numero)
    except (EmptyPage, ValueError):
        pagina = paginador.page(1)

    total = paginador.count
    desde = pagina.start_index() if total else 0
    hasta = pagina.end_index() if total else 0

    # Parámetros de la URL sin «pagina», para que los filtros sobrevivan al salto.
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return {
        "pagina": pagina,
        "paginador": paginador,
        "total": total,
        "desde": desde,
        "hasta": hasta,
        "parametros_url": parametros.urlencode(),
    }


def respuesta_exito(mensaje: str, recargar: bool = True,
                    evento_extra: dict | None = None) -> HttpResponse:
    """
    Devuelve una respuesta vacía que le dice a HTMX que cierre el modal,
    muestre un toast y recargue la tabla.

    :param mensaje: texto del toast.
    :param recargar: si la tabla debe volver a pedirse al servidor.
    :param evento_extra: eventos adicionales para el cliente.
    """
    # El orden importa: HTMX dispara los eventos sobre el elemento que hizo la
    # petición, en el orden de esta tabla. «kardexRecargar» tiene que salir antes
    # de que «kardexCerrarModal» quite el modal del DOM; si no, el evento ya no
    # burbujea hasta <body> y la tabla se queda con los datos viejos.
    eventos: dict[str, Any] = {}
    if recargar:
        eventos["kardexRecargar"] = True
    eventos["kardexToast"] = {"texto": mensaje, "tipo": "ok"}
    eventos["kardexCerrarModal"] = True
    if evento_extra:
        eventos.update(evento_extra)

    respuesta = HttpResponse(status=204)
    respuesta["HX-Trigger"] = json.dumps(eventos)
    return respuesta


def respuesta_aviso(mensaje: str, tipo: str = "alerta") -> HttpResponse:
    """Devuelve una respuesta que solo muestra un toast, sin cerrar el modal."""
    respuesta = HttpResponse(status=204)
    respuesta["HX-Trigger"] = json.dumps({"kardexToast": {"texto": mensaje, "tipo": tipo}})
    return respuesta


def es_htmx(request: HttpRequest) -> bool:
    """Indica si la petición viene de HTMX."""
    return request.headers.get("HX-Request") == "true"


def entero_o_none(valor: Any) -> int | None:
    """Convierte a entero un parámetro de la URL; devuelve ``None`` si no se puede."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Subida de archivos — Seguridad #11 (OWASP A03 / A08)
# ---------------------------------------------------------------------------
_CARACTERES_PROHIBIDOS = re.compile(r"[^A-Za-z0-9._-]")


def sanear_nombre_archivo(nombre: str) -> str:
    """
    Devuelve un nombre de archivo seguro: sin rutas, sin caracteres raros y
    con largo acotado.
    """
    base = os.path.basename(nombre or "").replace("\\", "/").split("/")[-1]
    base = _CARACTERES_PROHIBIDOS.sub("_", base).lstrip(".")
    if not base:
        base = "archivo"
    raiz, punto, extension = base.rpartition(".")
    if punto:
        return f"{raiz[:80]}.{extension[:10]}"
    return base[:80]


def validar_archivo_subido(archivo) -> None:
    """
    Comprueba extensión y tamaño de un archivo subido, del lado del servidor.

    :raises ValidationError: si la extensión no está permitida o excede el tope.
    """
    if archivo is None:
        return

    nombre = sanear_nombre_archivo(getattr(archivo, "name", ""))
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in settings.EXTENSIONES_PERMITIDAS:
        permitidas = ", ".join(settings.EXTENSIONES_PERMITIDAS)
        raise ValidationError(f"Extensión no permitida. Se aceptan: {permitidas}.")

    tope = settings.TAMANO_MAXIMO_ARCHIVO_MB * 1024 * 1024
    if getattr(archivo, "size", 0) > tope:
        raise ValidationError(
            f"El archivo supera el máximo de {settings.TAMANO_MAXIMO_ARCHIVO_MB} MB."
        )
