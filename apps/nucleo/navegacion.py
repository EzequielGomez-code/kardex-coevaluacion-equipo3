"""
Entradas de menú que aporta la app ``nucleo``.

Cada app declara aquí su lista ``ENTRADAS`` y el layout la recoge sola. Así
Arturo, Cristian y Francisco agregan su sección sin tocar ``base.html``
(punto 5.1 del brief).

Formato de cada entrada:

``seccion``  título del grupo en la barra lateral.
``titulo``   texto del enlace.
``url``      nombre de ruta de Django (``espacio:nombre``).
``permiso``  clave que debe tener el usuario; ``None`` si es para todos.
``icono``    identificador del símbolo SVG en ``componentes/iconos.html``.
``orden``    entero; ordena dentro de la sección.
"""

ENTRADAS: list[dict] = [
    {
        "seccion": "Operación",
        "titulo": "Panel",
        "url": "nucleo:panel",
        "permiso": None,
        "icono": "panel",
        "orden": 10,
    },
    {
        "seccion": "Administración",
        "titulo": "Almacenes",
        "url": "nucleo:almacenes",
        "permiso": "almacen.gestionar",
        "icono": "almacen",
        "orden": 10,
    },
    {
        "seccion": "Administración",
        "titulo": "Usuarios",
        "url": "nucleo:usuarios",
        "permiso": "usuario.gestionar",
        "icono": "usuarios",
        "orden": 20,
    },
    {
        "seccion": "Administración",
        "titulo": "Roles y permisos",
        "url": "nucleo:roles",
        "permiso": "usuario.gestionar",
        "icono": "roles",
        "orden": 30,
    },
    {
        "seccion": "Administración",
        "titulo": "Auditoría",
        "url": "nucleo:auditoria",
        "permiso": "reporte.ver",
        "icono": "auditoria",
        "orden": 40,
    },
]
