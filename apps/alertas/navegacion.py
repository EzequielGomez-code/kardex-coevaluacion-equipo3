"""
Entrada de menú que aporta la app ``alertas``.

El layout la recoge sola desde ``apps/*/navegacion.py``; no hay que tocar
``base.html`` (punto 5.1 del brief).
"""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Alertas",
        "url": "alertas:indice",
        "permiso": "alerta.ver",
        "icono": "alertas",
        "orden": 30,
    },
]
