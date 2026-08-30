"""
Vistas de Alertas — las construye Francisco.

Cada vista comprueba su permiso en el servidor con ``@requiere_permiso``
(Seguridad #4 del brief) y delega en un servicio. Ninguna vista consulta el
ORM directamente.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.nucleo.decoradores import requiere_permiso


@requiere_permiso("alerta.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """
    Pantalla de entrada del módulo, todavía sin construir.

    Sirve de andamio: deja la ruta, el permiso y el layout ya resueltos para
    que Francisco solo tenga que reemplazar el cuerpo.
    """
    contexto = {
        "titulo": "Alertas",
        "migas": [{"texto": "Inventario"}, {"texto": "Alertas"}],
        "modulo": "Alertas",
        "responsable": "Francisco",
        "alcance": "reglas de alerta, notificaciones y proveedores",
    }
    return render(request, "alertas/indice.html", contexto)
