"""Entradas de menú que aporta la app ``movimientos``."""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Movimientos",
        "url": "movimientos:indice",
        "permiso": "movimiento.ver",
        "icono": "movimientos",
        "orden": 20,
    },
    {
        "seccion": "Inventario",
        "titulo": "Existencias",
        "url": "movimientos:existencias",
        "permiso": "movimiento.ver",
        "icono": "almacen",
        "orden": 21,
    },
    {
        "seccion": "Inventario",
        "titulo": "Aprobaciones",
        "url": "movimientos:aprobaciones",
        "permiso": "movimiento.aprobar",
        "icono": "candado",
        "orden": 22,
    },
    {
        "seccion": "Sistema",
        "titulo": "Tipos de movimiento",
        "url": "movimientos:tipos",
        "permiso": "tipo_movimiento.gestionar",
        "icono": "movimientos",
        "orden": 40,
    },
]
