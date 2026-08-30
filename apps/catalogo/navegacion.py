"""
Entrada de menú que aporta la app ``catalogo``.

El layout la recoge sola desde ``apps/*/navegacion.py``; no hay que tocar
``base.html`` (punto 5.1 del brief).
"""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Catálogo",
        "url": "catalogo:indice",
        "permiso": "articulo.ver",
        "icono": "catalogo",
        "orden": 10,
    },
]
