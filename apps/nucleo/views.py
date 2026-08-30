"""
Vistas del núcleo: acceso, panel, almacenes, usuarios, roles y auditoría.

Ninguna vista consulta el ORM: todas pasan por los servicios (regla de capas
del punto 3). Cada vista que modifica datos comprueba el permiso en el
servidor con ``@requiere_permiso`` (Seguridad #4).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.nucleo.decoradores import requiere_permiso, requiere_sesion
from apps.nucleo.forms import (
    FormularioAlmacen,
    FormularioInicioSesion,
    FormularioRol,
    FormularioUsuario,
)
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.repositories import RepositorioPermisos
from apps.nucleo.services import (
    ServicioAlmacenes,
    ServicioAuditoria,
    ServicioRoles,
    ServicioUsuarios,
)
from apps.nucleo.utilidades import entero_o_none, paginar, respuesta_exito

# Importación diferida en tiempo de carga del módulo: ``configuracion`` depende
# de ``nucleo`` para sus formularios, así que se toma solo lo necesario.
from apps.configuracion.forms import FormularioCamposDinamicos  # noqa: E402  isort:skip

# Nombre lógico con el que los campos personalizados se cuelgan del almacén.
ENTIDAD_ALMACEN = "Almacen"

# ---------------------------------------------------------------------------
# Definición de columnas de las tablas.
#
# Van aquí y no en la plantilla para que el componente ``tabla.html`` siga
# siendo genérico: los tres módulos declaran las suyas de la misma forma.
# ---------------------------------------------------------------------------
COLUMNAS_ALMACEN = [
    {"etiqueta": "Código", "clave": "codigo"},
    {"etiqueta": "Nombre", "clave": "nombre"},
    {"etiqueta": "Dirección"},
    {"etiqueta": "Encargado"},
    {"etiqueta": "Estado"},
]

COLUMNAS_USUARIO = [
    {"etiqueta": "Acceso", "clave": "username"},
    {"etiqueta": "Nombre completo"},
    {"etiqueta": "Correo"},
    {"etiqueta": "Rol"},
    {"etiqueta": "Último acceso"},
    {"etiqueta": "Estado"},
]

COLUMNAS_ROL = [
    {"etiqueta": "Rol", "clave": "nombre"},
    {"etiqueta": "Descripción"},
    {"etiqueta": "Permisos", "clase": "num"},
    {"etiqueta": "Usuarios", "clase": "num"},
    {"etiqueta": "Origen"},
]

COLUMNAS_AUDITORIA = [
    {"etiqueta": "Fecha y hora"},
    {"etiqueta": "Usuario"},
    {"etiqueta": "Acción"},
    {"etiqueta": "Entidad"},
    {"etiqueta": "Identificador"},
    {"etiqueta": "Detalle"},
    {"etiqueta": "IP"},
]


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def iniciar_sesion(request: HttpRequest) -> HttpResponse:
    """
    Formulario de acceso.

    El conteo de intentos fallidos lo lleva django-axes por debajo
    (Seguridad #7): a los 5 fallos bloquea la combinación IP + usuario.
    """
    if request.user.is_authenticated:
        return redirect("nucleo:panel")

    formulario = FormularioInicioSesion(request, data=request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        usuario = formulario.get_user()
        login(request, usuario)
        ServicioAuditoria.registrar(
            entidad="Sesion",
            entidad_id=usuario.pk,
            accion=RegistroAuditoria.Accion.INICIAR_SESION,
            detalle={"usuario": usuario.username},
            usuario=usuario,
        )
        destino = request.GET.get("siguiente") or reverse("nucleo:panel")
        # Solo se acepta un destino interno: evita redirecciones abiertas (OWASP A01).
        if not destino.startswith("/"):
            destino = reverse("nucleo:panel")
        return redirect(destino)

    return render(
        request,
        "nucleo/iniciar_sesion.html",
        {"formulario": formulario, "titulo": "Acceso al sistema"},
    )


@requiere_sesion
def cerrar_sesion(request: HttpRequest) -> HttpResponse:
    """Cierra la sesión y deja constancia en la auditoría."""
    usuario = request.user
    ServicioAuditoria.registrar(
        entidad="Sesion",
        entidad_id=usuario.pk,
        accion=RegistroAuditoria.Accion.CERRAR_SESION,
        detalle={"usuario": usuario.username},
        usuario=usuario,
    )
    logout(request)
    return redirect("nucleo:iniciar_sesion")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
@requiere_sesion
def panel(request: HttpRequest) -> HttpResponse:
    """Pantalla de entrada, con el estado general y la actividad reciente."""
    almacenes_activos = ServicioAlmacenes.listar(estado="activo")
    contexto = {
        "titulo": "Panel",
        "migas": [{"texto": "Panel"}],
        "almacenes": almacenes_activos,
        "total_almacenes": almacenes_activos.count(),
        "total_usuarios": ServicioUsuarios.listar(estado="activo").count(),
        "total_roles": ServicioRoles.listar().count(),
        "actividad": ServicioAuditoria.listar()[:12],
    }
    return render(request, "nucleo/panel.html", contexto)


# ---------------------------------------------------------------------------
# Almacenes
# ---------------------------------------------------------------------------
@requiere_permiso("almacen.gestionar")
def almacenes(request: HttpRequest) -> HttpResponse:
    """Listado de almacenes con filtros en la URL."""
    busqueda = request.GET.get("busqueda", "").strip()
    estado = request.GET.get("estado", "")
    consulta = ServicioAlmacenes.listar(busqueda=busqueda, estado=estado)

    contexto = {
        "titulo": "Almacenes",
        "migas": [{"texto": "Administración"}, {"texto": "Almacenes"}],
        "busqueda": busqueda,
        "estado": estado,
        "columnas_almacen": COLUMNAS_ALMACEN,
        **paginar(request, consulta),
    }
    return render(request, "nucleo/almacenes.html", contexto)


@requiere_permiso("almacen.gestionar")
@require_http_methods(["GET", "POST"])
def almacen_formulario(request: HttpRequest, almacen_id: int | None = None) -> HttpResponse:
    """
    Alta o edición de un almacén dentro de un modal HTMX.

    Al formulario fijo se le suman los campos que el usuario haya definido para
    la entidad ``Almacen`` desde «Campos personalizados». Ese es el circuito
    completo del criterio 9.5 del brief: se crea el campo en pantalla y aparece
    aquí sin tocar código.
    """
    almacen = ServicioAlmacenes.obtener(almacen_id) if almacen_id else None
    if almacen_id and almacen is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioAlmacen(request.POST, instance=almacen)
        personalizados = FormularioCamposDinamicos(
            request.POST, entidad=ENTIDAD_ALMACEN, instancia=almacen
        )
        if formulario.is_valid() and personalizados.is_valid():
            datos = formulario.cleaned_data
            try:
                if almacen:
                    guardado = ServicioAlmacenes.actualizar(
                        almacen,
                        codigo=datos["codigo"],
                        nombre=datos["nombre"],
                        direccion=datos["direccion"],
                        encargado=datos["encargado"],
                        activo=datos["activo"],
                    )
                    mensaje = f"Almacén {datos['codigo']} actualizado."
                else:
                    guardado = ServicioAlmacenes.crear(
                        codigo=datos["codigo"],
                        nombre=datos["nombre"],
                        direccion=datos["direccion"],
                        encargado=datos["encargado"],
                        activo=datos["activo"],
                    )
                    mensaje = f"Almacén {datos['codigo']} creado."
                personalizados.guardar(guardado)
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioAlmacen(instance=almacen)
        personalizados = FormularioCamposDinamicos(
            entidad=ENTIDAD_ALMACEN, instancia=almacen
        )

    contexto = {
        "formulario": formulario,
        "campos_personalizados": personalizados,
        "titulo_modal": "Editar almacén" if almacen else "Nuevo almacén",
        "destino": (
            reverse("nucleo:almacen_editar", args=[almacen.pk])
            if almacen
            else reverse("nucleo:almacen_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if almacen else "Crear almacén",
    }
    return render(request, "nucleo/almacen_formulario.html", contexto)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@requiere_permiso("usuario.gestionar")
def usuarios(request: HttpRequest) -> HttpResponse:
    """Listado de usuarios con filtros por rol y estado."""
    busqueda = request.GET.get("busqueda", "").strip()
    rol_id = entero_o_none(request.GET.get("rol"))
    estado = request.GET.get("estado", "")
    consulta = ServicioUsuarios.listar(busqueda=busqueda, rol_id=rol_id, estado=estado)

    contexto = {
        "titulo": "Usuarios",
        "migas": [{"texto": "Administración"}, {"texto": "Usuarios"}],
        "busqueda": busqueda,
        "rol_id": rol_id,
        "estado": estado,
        "roles": ServicioRoles.listar(),
        "columnas_usuario": COLUMNAS_USUARIO,
        **paginar(request, consulta),
    }
    return render(request, "nucleo/usuarios.html", contexto)


@requiere_permiso("usuario.gestionar")
@require_http_methods(["GET", "POST"])
def usuario_formulario(request: HttpRequest, usuario_id: int | None = None) -> HttpResponse:
    """Alta o edición de un usuario dentro de un modal HTMX."""
    usuario = ServicioUsuarios.obtener(usuario_id) if usuario_id else None
    if usuario_id and usuario is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioUsuario(request.POST, es_edicion=usuario is not None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if usuario:
                    ServicioUsuarios.actualizar(
                        usuario,
                        nombre_completo=datos["nombre_completo"],
                        email=datos["email"],
                        telefono=datos["telefono"],
                        rol=datos["rol"],
                        activo=datos["activo"],
                        contrasena=datos["contrasena"],
                    )
                    mensaje = f"Usuario {usuario.username} actualizado."
                else:
                    creado = ServicioUsuarios.crear(
                        username=datos["username"],
                        nombre_completo=datos["nombre_completo"],
                        email=datos["email"],
                        telefono=datos["telefono"],
                        rol=datos["rol"],
                        contrasena=datos["contrasena"],
                        activo=datos["activo"],
                    )
                    mensaje = f"Usuario {creado.username} creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if usuario:
            inicial = {
                "username": usuario.username,
                "nombre_completo": usuario.nombre_completo,
                "email": usuario.email,
                "telefono": usuario.telefono,
                "rol": usuario.rol_id,
                "activo": usuario.activo,
            }
        formulario = FormularioUsuario(initial=inicial, es_edicion=usuario is not None)

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar usuario" if usuario else "Nuevo usuario",
        "destino": (
            reverse("nucleo:usuario_editar", args=[usuario.pk])
            if usuario
            else reverse("nucleo:usuario_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if usuario else "Crear usuario",
    }
    return render(request, "nucleo/usuario_formulario.html", contexto)


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------
@requiere_permiso("usuario.gestionar")
def roles(request: HttpRequest) -> HttpResponse:
    """Listado de roles con la cantidad de usuarios de cada uno."""
    busqueda = request.GET.get("busqueda", "").strip()
    contexto = {
        "titulo": "Roles y permisos",
        "migas": [{"texto": "Administración"}, {"texto": "Roles y permisos"}],
        "busqueda": busqueda,
        "columnas_rol": COLUMNAS_ROL,
        **paginar(request, ServicioRoles.listar(busqueda=busqueda)),
    }
    return render(request, "nucleo/roles.html", contexto)


@requiere_permiso("usuario.gestionar")
@require_http_methods(["GET", "POST"])
def rol_formulario(request: HttpRequest, rol_id: int | None = None) -> HttpResponse:
    """Alta o edición de un rol, con los permisos agrupados por módulo."""
    rol = ServicioRoles.obtener(rol_id) if rol_id else None
    if rol_id and rol is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioRol(request.POST)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if rol:
                    ServicioRoles.actualizar(
                        rol,
                        nombre=datos["nombre"],
                        descripcion=datos["descripcion"],
                        claves_permiso=datos["permisos"],
                    )
                    mensaje = f"Rol {datos['nombre']} actualizado."
                else:
                    ServicioRoles.crear(
                        nombre=datos["nombre"],
                        descripcion=datos["descripcion"],
                        claves_permiso=datos["permisos"],
                    )
                    mensaje = f"Rol {datos['nombre']} creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if rol:
            inicial = {
                "nombre": rol.nombre,
                "descripcion": rol.descripcion,
                "permisos": sorted(ServicioRoles.claves_de(rol)),
            }
        formulario = FormularioRol(initial=inicial)

    seleccionados = set(formulario["permisos"].value() or [])
    contexto = {
        "formulario": formulario,
        "rol": rol,
        "grupos_permiso": RepositorioPermisos.agrupados_por_modulo(),
        "permisos_marcados": seleccionados,
        "titulo_modal": "Editar rol" if rol else "Nuevo rol",
        "destino": (
            reverse("nucleo:rol_editar", args=[rol.pk]) if rol else reverse("nucleo:rol_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if rol else "Crear rol",
    }
    return render(request, "nucleo/rol_formulario.html", contexto)


@requiere_permiso("usuario.gestionar")
@require_http_methods(["POST"])
def rol_eliminar(request: HttpRequest, rol_id: int) -> HttpResponse:
    """Elimina un rol si no es del sistema y no tiene usuarios."""
    rol = ServicioRoles.obtener(rol_id)
    if rol is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        nombre = rol.nombre
        ServicioRoles.eliminar(rol)
    except ValidationError as error:
        from apps.nucleo.utilidades import respuesta_aviso  # pylint: disable=import-outside-toplevel

        return respuesta_aviso(" ".join(error.messages))
    return respuesta_exito(f"Rol {nombre} eliminado.")


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------
@requiere_permiso("reporte.ver")
def auditoria(request: HttpRequest) -> HttpResponse:
    """Rastro de auditoría, solo lectura, con filtros en la URL."""
    entidad = request.GET.get("entidad", "")
    accion = request.GET.get("accion", "")
    busqueda = request.GET.get("busqueda", "").strip()

    consulta = ServicioAuditoria.listar(entidad=entidad, accion=accion, busqueda=busqueda)
    contexto = {
        "titulo": "Auditoría",
        "migas": [{"texto": "Administración"}, {"texto": "Auditoría"}],
        "entidad": entidad,
        "accion": accion,
        "busqueda": busqueda,
        "entidades": ServicioAuditoria.entidades(),
        "acciones": RegistroAuditoria.Accion.choices,
        "columnas_auditoria": COLUMNAS_AUDITORIA,
        **paginar(request, consulta, por_pagina=40),
    }
    return render(request, "nucleo/auditoria.html", contexto)


# ---------------------------------------------------------------------------
# Perfil y utilidades
# ---------------------------------------------------------------------------
@requiere_sesion
def perfil(request: HttpRequest) -> HttpResponse:
    """Ficha del usuario en sesión, con sus permisos efectivos."""
    contexto = {
        "titulo": "Mi perfil",
        "migas": [{"texto": "Mi perfil"}],
        "permisos": sorted(request.user.claves_de_permiso()),
    }
    return render(request, "nucleo/perfil.html", contexto)


@requiere_sesion
def buscador(request: HttpRequest) -> HttpResponse:
    """
    Buscador global de la barra superior.

    De momento resuelve almacenes y usuarios; catálogo, movimientos y alertas
    se enganchan aquí cuando esas apps existan.
    """
    termino = request.GET.get("q", "").strip()
    resultados: list[dict] = []

    if termino and request.user.tiene_permiso("almacen.gestionar"):
        for almacen in ServicioAlmacenes.listar(busqueda=termino)[:5]:
            resultados.append(
                {
                    "grupo": "Almacenes",
                    "texto": str(almacen),
                    "destino": reverse("nucleo:almacenes") + f"?busqueda={almacen.codigo}",
                }
            )

    if termino and request.user.tiene_permiso("usuario.gestionar"):
        for usuario in ServicioUsuarios.listar(busqueda=termino)[:5]:
            resultados.append(
                {
                    "grupo": "Usuarios",
                    "texto": str(usuario),
                    "destino": reverse("nucleo:usuarios") + f"?busqueda={usuario.username}",
                }
            )

    return render(
        request,
        "componentes/resultados_busqueda.html",
        {"resultados": resultados, "termino": termino},
    )


def _volcar_errores(formulario, error: ValidationError) -> None:
    """Traslada los errores de un servicio a los campos del formulario."""
    if hasattr(error, "error_dict"):
        for campo, errores in error.message_dict.items():
            destino = campo if campo in formulario.fields else None
            for mensaje in errores:
                formulario.add_error(destino, mensaje)
    else:
        for mensaje in error.messages:
            formulario.add_error(None, mensaje)


# ---------------------------------------------------------------------------
# Páginas de error
# ---------------------------------------------------------------------------
def error_403(request: HttpRequest, exception=None) -> HttpResponse:  # noqa: ARG001
    """Página 403: el usuario está autenticado pero su rol no alcanza."""
    return render(
        request,
        "nucleo/error.html",
        {
            "codigo": "403",
            "titulo": "Acceso denegado",
            "detalle": "Su rol no tiene permiso para ver esta pantalla. "
                       "Si cree que es un error, contacte al administrador de TI.",
        },
        status=403,
    )


def error_404(request: HttpRequest, exception=None) -> HttpResponse:  # noqa: ARG001
    """Página 404."""
    return render(
        request,
        "nucleo/error.html",
        {
            "codigo": "404",
            "titulo": "Pantalla no encontrada",
            "detalle": "La dirección solicitada no existe en el sistema.",
        },
        status=404,
    )


def error_500(request: HttpRequest) -> HttpResponse:
    """Página 500. No revela la traza al usuario final (Seguridad #6)."""
    return render(
        request,
        "nucleo/error.html",
        {
            "codigo": "500",
            "titulo": "Error interno",
            "detalle": "Ocurrió un problema al procesar la solicitud. "
                       "El incidente quedó registrado.",
            "sin_menu": not settings.DEBUG,
        },
        status=500,
    )
