"""Entradas de menú que aporta la app ``alertas``."""

ENTRADAS: list[dict] = [
    {
        "seccion": "Inventario",
        "titulo": "Alertas",
        "url": "alertas:indice",
        "permiso": "alerta.ver",
        "icono": "alertas",
        "orden": 30,
    },
    {
        "seccion": "Sistema",
        "titulo": "Reglas de alerta",
        "url": "alertas:reglas",
        "permiso": "alerta.configurar",
        "icono": "alertas",
        "orden": 41,
    },
]
