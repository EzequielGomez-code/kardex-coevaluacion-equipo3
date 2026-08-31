"""
Procesadores de contexto del núcleo.

Arman el menú lateral recorriendo ``apps/*/navegacion.py`` y publican los datos
de versión que se muestran en el pie de página.
"""

from __future__ import annotations

import functools
import importlib
import logging
import subprocess  # nosec B404 — solo se usa para leer el hash del commit local

from django.apps import apps as registro_de_apps
from django.conf import settings
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

registro = logging.getLogger("kardex.nucleo")

# Orden en el que se pintan las secciones de la barra lateral.
ORDEN_DE_SECCIONES = ["Operación", "Inventario", "Reportes", "Administración", "Sistema"]


@functools.lru_cache(maxsize=1)
def _entradas_declaradas() -> list[dict]:
    """
    Recoge las entradas de menú de todas las apps propias.

    El resultado se memoriza porque los módulos de navegación son estáticos:
    solo cambian cuando se reinicia el proceso.
    """
    recogidas: list[dict] = []
    for configuracion_app in registro_de_apps.get_app_configs():
        if not configuracion_app.name.startswith("apps."):
            continue
        try:
            modulo = importlib.import_module(f"{configuracion_app.name}.navegacion")
        except ModuleNotFoundError:
            continue
        recogidas.extend(getattr(modulo, "ENTRADAS", []))
    return recogidas


def navegacion_lateral(request: HttpRequest) -> dict:
    """
    Devuelve el menú lateral ya filtrado por los permisos del usuario.

    Una entrada sin ``permiso`` la ve cualquier sesión iniciada. Ocultar el
    enlace es solo comodidad: la vista vuelve a comprobar el permiso
    (Seguridad #4).
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"secciones_menu": []}

    ruta_actual = request.path
    por_seccion: dict[str, list[dict]] = {}

    for entrada in _entradas_declaradas():
        clave = entrada.get("permiso")
        if clave and not usuario.tiene_permiso(clave):
            continue
        try:
            destino = reverse(entrada["url"])
        except NoReverseMatch:
            # Una app todavía sin construir no debe tumbar el menú de las demás.
            registro.debug("Ruta no resuelta en el menú: %s", entrada["url"])
            continue

        por_seccion.setdefault(entrada["seccion"], []).append(
            {
                "titulo": entrada["titulo"],
                "destino": destino,
                "icono": entrada.get("icono", "punto"),
                "orden": entrada.get("orden", 100),
                "activa": ruta_actual == destino
                or (destino != "/" and ruta_actual.startswith(destino)),
            }
        )

    secciones = []
    nombres = sorted(
        por_seccion,
        key=lambda nombre: (
            ORDEN_DE_SECCIONES.index(nombre) if nombre in ORDEN_DE_SECCIONES else 99,
            nombre,
        ),
    )
    for nombre in nombres:
        enlaces = sorted(por_seccion[nombre], key=lambda enlace: enlace["orden"])
        secciones.append({"nombre": nombre, "enlaces": enlaces})

    return {"secciones_menu": secciones}


@functools.lru_cache(maxsize=1)
def _commit_corto() -> str:
    """Devuelve el hash corto del commit actual, o cadena vacía si no hay git."""
    try:
        salida = subprocess.run(  # nosec B603 B607 — comando fijo, sin entrada del usuario
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            cwd=settings.BASE_DIR,
        )
        return salida.stdout.strip() if salida.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def datos_de_version(request: HttpRequest) -> dict:  # pylint: disable=unused-argument
    """Publica nombre, versión y commit corto para el pie de página."""
    return {
        "nombre_sistema": settings.NOMBRE_SISTEMA,
        "nombre_empresa": settings.NOMBRE_EMPRESA,
        "version_kardex": settings.VERSION_KARDEX,
        "commit_corto": _commit_corto(),
    }
