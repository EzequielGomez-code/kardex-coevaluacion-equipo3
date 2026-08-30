"""Entradas de menú que aporta la app ``configuracion``."""

ENTRADAS: list[dict] = [
    {
        "seccion": "Sistema",
        "titulo": "Parámetros",
        "url": "configuracion:parametros",
        "permiso": "configuracion.gestionar",
        "icono": "ajustes",
        "orden": 10,
    },
    {
        "seccion": "Sistema",
        "titulo": "Campos personalizados",
        "url": "configuracion:campos",
        "permiso": "configuracion.gestionar",
        "icono": "campos",
        "orden": 20,
    },
    {
        "seccion": "Sistema",
        "titulo": "Etiquetas",
        "url": "configuracion:etiquetas",
        "permiso": "configuracion.gestionar",
        "icono": "etiquetas",
        "orden": 30,
    },
]
