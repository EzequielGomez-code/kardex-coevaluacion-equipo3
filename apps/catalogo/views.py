"""
Vistas de Catálogo — las construye Arturo.

Cada vista comprueba su permiso en el servidor con ``@requiere_permiso``
(Seguridad #4 del brief) y delega en un servicio. Ninguna vista consulta el
ORM directamente.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.nucleo.decoradores import requiere_permiso


@requiere_permiso("articulo.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """
    Pantalla de entrada del módulo, todavía sin construir.

    Sirve de andamio: deja la ruta, el permiso y el layout ya resueltos para
    que Arturo solo tenga que reemplazar el cuerpo.
    """
    contexto = {
        "titulo": "Catálogo",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}],
        "modulo": "Catálogo",
        "responsable": "Arturo",
        "alcance": "artículos, categorías, unidades de medida y existencias",
    }
    return render(request, "catalogo/indice.html", contexto)
