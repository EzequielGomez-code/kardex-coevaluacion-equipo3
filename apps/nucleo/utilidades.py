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
            por_pagina: int | None = None) -> dict:
    """
    Pagina un conjunto de resultados y arma los datos que usa ``paginacion.html``.

    :param request: petición en curso; se lee ``?pagina=`` de la URL.
    :param consulta: cualquier iterable o ``QuerySet``.
    :param por_pagina: cantidad de filas por página. Si se omite, se toma del
        parámetro del sistema ``filas_por_pagina``, editable desde pantalla.
    :returns: diccionario con la página, el rango mostrado y el total.
    """
    if por_pagina is None:
        # Importación diferida: evita un ciclo entre nucleo y configuracion,
        # igual que en decoradores.py.
        from apps.configuracion.services import ServicioParametros

        por_pagina = ServicioParametros.obtener("filas_por_pagina", POR_PAGINA_POR_OMISION)

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


def ordenar(consulta: Any, request: HttpRequest, permitidas: dict[str, str]) -> Any:
    """
    Ordena un ``QuerySet`` según ``?orden=`` en la URL, validado contra una
    lista blanca de columnas.

    El formato del parámetro es el que ya pinta ``componentes/tabla.html``:
    ``?orden=<clave>`` para ascendente y ``?orden=<clave>-desc`` para
    descendente. Una clave que no está en ``permitidas`` se ignora en
    silencio y la consulta vuelve sin ordenar, para que una URL manipulada
    no permita ordenar por una columna no expuesta.

    :param consulta: ``QuerySet`` a ordenar.
    :param request: petición en curso.
    :param permitidas: diccionario ``clave pública -> campo real del modelo``.
    :returns: el mismo ``QuerySet``, ordenado si la clave es válida.
    """
    clave = request.GET.get("orden", "")
    if not clave:
        return consulta

    descendente = clave.endswith("-desc")
    clave_base = clave[: -len("-desc")] if descendente else clave

    campo = permitidas.get(clave_base)
    if campo is None:
        return consulta

    return consulta.order_by(f"-{campo}" if descendente else campo)


def fichas_de_filtro(request: HttpRequest, campos: dict[str, str],
                     etiquetas_valor: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """
    Arma las fichas de filtro activo de una pantalla de listado.

    Cada ficha trae ya resuelta la URL que la quita sin tocar los demás
    filtros ni la página en curso (BRIEF 02, punto 2.4).

    :param request: petición en curso.
    :param campos: ``{parametro_de_la_url: etiqueta_visible}``, por ejemplo
        ``{"busqueda": "Busca", "estado": "Estado"}``.
    :param etiquetas_valor: ``{parametro: {valor_crudo: etiqueta_legible}}``
        para traducir un valor como ``"activo"`` a ``"Activos"``. Un
        parámetro ausente de este diccionario muestra el valor tal cual.
    :returns: lista de ``{"texto": str, "url_quitar": str}``; vacía si no hay
        ningún filtro activo.
    """
    etiquetas_valor = etiquetas_valor or {}
    fichas = []

    for parametro, etiqueta in campos.items():
        valor = request.GET.get(parametro, "").strip()
        if not valor:
            continue

        texto_valor = etiquetas_valor.get(parametro, {}).get(valor, valor)
        restantes = request.GET.copy()
        restantes.pop(parametro, None)
        restantes.pop("pagina", None)
        cadena = restantes.urlencode()

        fichas.append(
            {
                "texto": f"{etiqueta}: {texto_valor}",
                "url_quitar": f"{request.path}?{cadena}" if cadena else request.path,
            }
        )
    return fichas


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
