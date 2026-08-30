"""
Vistas de Movimientos — las construye Cristian.

Cada vista comprueba su permiso en el servidor con ``@requiere_permiso``
(Seguridad #4 del brief) y delega en un servicio. Ninguna vista consulta el
ORM directamente.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.nucleo.decoradores import requiere_permiso


@requiere_permiso("movimiento.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """
    Pantalla de entrada del módulo, todavía sin construir.

    Sirve de andamio: deja la ruta, el permiso y el layout ya resueltos para
    que Cristian solo tenga que reemplazar el cuerpo.
    """
    contexto = {
        "titulo": "Movimientos",
        "migas": [{"texto": "Inventario"}, {"texto": "Movimientos"}],
        "modulo": "Movimientos",
        "responsable": "Cristian",
        "alcance": "entradas, salidas, transferencias y el kardex valorado",
    }
    return render(request, "movimientos/indice.html", contexto)
