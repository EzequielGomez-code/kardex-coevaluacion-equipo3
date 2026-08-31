"""
Entrada de menú que aporta la app ``catalogo``.

El layout la recoge sola desde ``apps/*/navegacion.py``; no hay que tocar
``base.html`` (punto 5.1 del brief). Las demás pantallas del catálogo
(categorías, marcas, unidades, proveedores, clientes) se llegan desde las
pestañas de navegación interna que trae ``catalogo/_subnav.html``, no desde
entradas nuevas en la barra lateral.
"""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Catálogo",
        "url": "catalogo:articulos",
        "permiso": "articulo.ver",
        "icono": "catalogo",
        "orden": 10,
    },
]
