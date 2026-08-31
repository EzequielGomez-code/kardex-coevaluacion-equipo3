"""
Filtros y etiquetas de presentación.

Aplican el punto 5.4 del brief: fechas ``dd/mm/aaaa``, moneda ``RD$ 1,250.00``,
y códigos en tipografía mono. El símbolo de moneda no está escrito en el
código: sale del parámetro ``moneda``, editable desde la interfaz.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# Django exige que la instancia se llame «register»: es palabra clave del
# framework, no un nombre de dominio (punto 8 del brief).
register = template.Library()


def _a_decimal(valor: Any) -> Decimal | None:
    """Convierte a ``Decimal`` con tolerancia; devuelve ``None`` si no se puede."""
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None


@register.filter
def cantidad(valor: Any, decimales: int = 2) -> str:
    """Formatea un número con separador de miles y cantidad fija de decimales."""
    numero = _a_decimal(valor)
    if numero is None:
        return "—"
    return f"{numero:,.{decimales}f}"


@register.filter
def entero(valor: Any) -> str:
    """Formatea un número entero con separador de miles."""
    numero = _a_decimal(valor)
    if numero is None:
        return "—"
    return f"{numero:,.0f}"


@register.simple_tag(takes_context=True)
def moneda(context: dict, valor: Any) -> str:
    """
    Formatea un importe usando el símbolo del parámetro ``moneda``.

    Uso: ``{% moneda articulo.precio %}`` → ``RD$ 1,250.00``.
    """
    numero = _a_decimal(valor)
    simbolo = (context.get("parametros") or {}).get("moneda", "RD$")
    if numero is None:
        return "—"
    return f"{simbolo} {numero:,.2f}"


def _en_hora_local(valor: Any) -> Any:
    """
    Convierte una fecha y hora con zona a la zona configurada en TIME_ZONE.

    Sin esto las marcas se mostrarían en UTC, que es como las guarda la base.
    """
    if isinstance(valor, dt.datetime) and timezone.is_aware(valor):
        return timezone.localtime(valor)
    return valor


@register.filter
def fecha_corta(valor: Any) -> str:
    """Devuelve la fecha en formato ``dd/mm/aaaa``."""
    if not valor:
        return "—"
    return _en_hora_local(valor).strftime("%d/%m/%Y")


@register.filter
def fecha_hora(valor: Any) -> str:
    """Devuelve la fecha y hora en formato ``dd/mm/aaaa HH:MM``."""
    if not valor:
        return "—"
    return _en_hora_local(valor).strftime("%d/%m/%Y %H:%M")


@register.filter
def mono(valor: Any) -> str:
    """Envuelve un código, SKU o hash en tipografía monoespaciada."""
    if valor in (None, ""):
        return "—"
    return format_html('<span class="mono">{}</span>', valor)


@register.simple_tag
def icono(nombre: str, clase: str = "") -> str:
    """
    Inserta un ícono del sprite SVG.

    Los símbolos se definen una sola vez en ``componentes/iconos.html``; aquí
    solo se referencian, así que todos comparten trazo de 1.5 px y heredan el
    color del texto (punto 5.4 del brief).
    """
    clases = f"icono {clase}".strip()
    return mark_safe(  # nosec B308 — el nombre viene de la plantilla, no del usuario
        f'<svg class="{clases}" aria-hidden="true"><use href="#i-{nombre}"></use></svg>'
    )


@register.simple_tag(takes_context=True)
def url_con(context: dict, **cambios) -> str:
    """
    Reconstruye la URL actual cambiando solo los parámetros indicados.

    Sirve para los enlaces de ordenamiento y paginación sin perder los filtros
    ya aplicados (punto 5.4: los filtros van en la URL).
    """
    request = context["request"]
    parametros = request.GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ""):
            parametros.pop(clave, None)
        else:
            parametros[clave] = valor
    cadena = parametros.urlencode()
    return f"{request.path}?{cadena}" if cadena else request.path


@register.filter
def sangria(nivel: Any, marca: str = "— ") -> str:
    """
    Repite una marca tantas veces como el nivel indica, para insinuar
    profundidad en un árbol dentro de un elemento que no admite sangría real
    (por ejemplo, las opciones de un ``<select>``).
    """
    try:
        return mark_safe(marca * int(nivel))  # nosec B308 — la marca es fija, no viene del usuario
    except (TypeError, ValueError):
        return ""


@register.filter
def tiene_permiso(usuario: Any, clave: str) -> bool:
    """
    Comprueba en la plantilla si el usuario tiene una clave de permiso.

    El ``perms`` que trae Django de fábrica lee el sistema de permisos
    integrado; este proyecto tiene el suyo propio (``Rol`` → ``Permiso``), así
    que hace falta este filtro para preguntarlo desde una plantilla.
    Recuerde que esto solo oculta un enlace: el permiso que manda es el que
    verifica ``@requiere_permiso`` en el servidor (Seguridad #4).
    """
    if not getattr(usuario, "is_authenticated", False):
        return False
    return usuario.tiene_permiso(clave)


@register.filter
def get_item(diccionario: Any, clave: Any) -> Any:
    """
    Devuelve ``diccionario[clave]`` desde una plantilla.

    Django no permite indexar con una variable; este filtro lo resuelve para
    traducir códigos a etiquetas legibles.
    """
    try:
        return diccionario.get(clave, clave)
    except AttributeError:
        return clave


@register.filter
def clase_de_accion(accion: str) -> str:
    """Devuelve la variante de badge que corresponde a una acción de auditoría."""
    return {
        "crear": "badge--ok",
        "editar": "badge--aviso",
        "eliminar": "badge--alerta",
        "acceso_denegado": "badge--alerta",
        "iniciar_sesion": "badge--neutro",
        "cerrar_sesion": "badge--neutro",
        "exportar": "badge--neutro",
    }.get(accion, "badge--neutro")
