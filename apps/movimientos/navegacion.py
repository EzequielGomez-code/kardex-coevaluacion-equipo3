"""
Entrada de menú que aporta la app ``movimientos``.

El layout la recoge sola desde ``apps/*/navegacion.py``; no hay que tocar
``base.html`` (punto 5.1 del brief).
"""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Movimientos",
        "url": "movimientos:indice",
        "permiso": "movimiento.ver",
        "icono": "movimientos",
        "orden": 20,
    },
]
