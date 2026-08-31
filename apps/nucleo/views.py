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
    FormularioReiniciarDemo,
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
from apps.nucleo.utilidades import (
    entero_o_none,
    fichas_de_filtro,
    ordenar,
    paginar,
    respuesta_aviso,
    respuesta_exito,
)

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
PERMITIDAS_ALMACEN = {"codigo": "codigo", "nombre": "nombre"}

COLUMNAS_USUARIO = [
    {"etiqueta": "Acceso", "clave": "username"},
    {"etiqueta": "Nombre completo", "clave": "nombre_completo"},
    {"etiqueta": "Correo", "clave": "email"},
    {"etiqueta": "Rol"},
    {"etiqueta": "Último acceso", "clave": "ultimo_acceso"},
    {"etiqueta": "Estado"},
]
PERMITIDAS_USUARIO = {
    "username": "username",
    "nombre_completo": "nombre_completo",
    "email": "email",
    "ultimo_acceso": "last_login",
}

COLUMNAS_ROL = [
    {"etiqueta": "Rol", "clave": "nombre"},
    {"etiqueta": "Descripción"},
    {"etiqueta": "Permisos", "clase": "num"},
    {"etiqueta": "Usuarios", "clase": "num", "clave": "usuarios"},
    {"etiqueta": "Origen"},
]
PERMITIDAS_ROL = {"nombre": "nombre", "usuarios": "total_usuarios"}

COLUMNAS_AUDITORIA = [
    {"etiqueta": "Fecha y hora", "clave": "fecha"},
    {"etiqueta": "Usuario"},
    {"etiqueta": "Acción"},
    {"etiqueta": "Entidad"},
    {"etiqueta": "Identificador"},
    {"etiqueta": "Detalle"},
    {"etiqueta": "IP"},
]
PERMITIDAS_AUDITORIA = {"fecha": "creado_en"}

# Traducción de valores crudos a etiquetas legibles para las fichas de filtro.
ETIQUETAS_ESTADO = {"activo": "Activos", "inactivo": "Inactivos"}


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
ALTO_FILA_GRAFICO = 34
ANCHO_MAXIMO_BARRA = 260


def _geometria_grafico_barras(filas: list[dict]) -> dict:
    """
    Convierte ``[{almacen__codigo, total}, …]`` en coordenadas SVG listas
    para pintar, para que la plantilla no tenga que hacer aritmética.
    """
    valor_maximo = max((fila["total"] for fila in filas), default=0) or 1
    barras = []
    for indice, fila in enumerate(filas):
        barras.append(
            {
                "codigo": fila["almacen__codigo"],
                "valor": fila["total"],
                "y": indice * ALTO_FILA_GRAFICO,
                "ancho": round((fila["total"] / valor_maximo) * ANCHO_MAXIMO_BARRA, 1),
            }
        )
    return {"barras": barras, "alto_total": len(filas) * ALTO_FILA_GRAFICO}


@requiere_sesion
def panel(request: HttpRequest) -> HttpResponse:
    """
    Pantalla de entrada: cifras clave, alertas abiertas, movimientos
    recientes y existencias por almacén — nunca tres tarjetas idénticas.

    Cada bloque se omite si el usuario no tiene el permiso que le
    correspondería a esa pantalla; el panel no es una puerta trasera para
    ver datos que la barra lateral ya le tiene ocultos.
    """
    almacenes_activos = ServicioAlmacenes.listar(estado="activo")
    contexto = {
        "titulo": "Panel",
        "migas": [{"texto": "Panel"}],
        "total_almacenes": almacenes_activos.count(),
        "total_usuarios": ServicioUsuarios.listar(estado="activo").count(),
        "total_roles": ServicioRoles.listar().count(),
        "actividad": ServicioAuditoria.listar()[:8],
    }

    if request.user.tiene_permiso("alerta.ver"):
        # Importación diferida: evita un ciclo entre nucleo y alertas.
        from apps.alertas.models import EstadoAlerta  # pylint: disable=import-outside-toplevel
        from apps.alertas.services import ServicioAlertas  # pylint: disable=import-outside-toplevel

        contexto["alertas_abiertas"] = ServicioAlertas.listar(estado=EstadoAlerta.ABIERTA)[:8]
        contexto["total_alertas_abiertas"] = ServicioAlertas.contar_abiertas()

    if request.user.tiene_permiso("movimiento.ver"):
        # Importación diferida: evita un ciclo entre nucleo y movimientos.
        from apps.movimientos.repositories import (
            RepositorioExistencias,  # pylint: disable=import-outside-toplevel
        )
        from apps.movimientos.services import ServicioMovimientos  # pylint: disable=import-outside-toplevel

        contexto["movimientos_recientes"] = ServicioMovimientos.listar()[:8]
        contexto["valor_inventario"] = RepositorioExistencias.total_valor()
        valor_por_almacen = RepositorioExistencias.valor_por_almacen()
        if valor_por_almacen:
            contexto["grafico_existencias"] = _geometria_grafico_barras(valor_por_almacen)

    return render(request, "nucleo/panel.html", contexto)


# ---------------------------------------------------------------------------
# Almacenes
# ---------------------------------------------------------------------------
@requiere_permiso("almacen.gestionar")
def almacenes(request: HttpRequest) -> HttpResponse:
    """Listado de almacenes con filtros en la URL."""
    busqueda = request.GET.get("busqueda", "").strip()
    estado = request.GET.get("estado", "")
    consulta = ordenar(
        ServicioAlmacenes.listar(busqueda=busqueda, estado=estado), request, PERMITIDAS_ALMACEN
    )

    contexto = {
        "titulo": "Almacenes",
        "migas": [{"texto": "Administración"}, {"texto": "Almacenes"}],
        "busqueda": busqueda,
        "estado": estado,
        "columnas_almacen": COLUMNAS_ALMACEN,
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "estado": "Estado"}, {"estado": ETIQUETAS_ESTADO}
        ),
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


@requiere_permiso("almacen.gestionar")
@require_http_methods(["POST"])
def almacen_eliminar(request: HttpRequest, almacen_id: int) -> HttpResponse:
    """Elimina un almacén sin movimientos registrados."""
    almacen = ServicioAlmacenes.obtener(almacen_id)
    if almacen is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        codigo = almacen.codigo
        ServicioAlmacenes.eliminar(almacen)
    except ValidationError as error:
        return respuesta_aviso(" ".join(error.messages))
    return respuesta_exito(f"Almacén {codigo} eliminado.")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@requiere_permiso("usuario.gestionar")
def usuarios(request: HttpRequest) -> HttpResponse:
    """Listado de usuarios con filtros por rol y estado."""
    busqueda = request.GET.get("busqueda", "").strip()
    rol_id = entero_o_none(request.GET.get("rol"))
    estado = request.GET.get("estado", "")
    consulta = ordenar(
        ServicioUsuarios.listar(busqueda=busqueda, rol_id=rol_id, estado=estado),
        request,
        PERMITIDAS_USUARIO,
    )

    roles_disponibles = ServicioRoles.listar()
    contexto = {
        "titulo": "Usuarios",
        "migas": [{"texto": "Administración"}, {"texto": "Usuarios"}],
        "busqueda": busqueda,
        "rol_id": rol_id,
        "estado": estado,
        "roles": roles_disponibles,
        "columnas_usuario": COLUMNAS_USUARIO,
        "fichas_filtro": fichas_de_filtro(
            request,
            {"busqueda": "Busca", "rol": "Rol", "estado": "Estado"},
            {
                "rol": {str(rol.pk): rol.nombre for rol in roles_disponibles},
                "estado": ETIQUETAS_ESTADO,
            },
        ),
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


@requiere_permiso("usuario.gestionar")
@require_http_methods(["POST"])
def usuario_alternar_estado(request: HttpRequest, usuario_id: int) -> HttpResponse:
    """Activa o desactiva un usuario."""
    usuario = ServicioUsuarios.obtener(usuario_id)
    if usuario is None:
        return respuesta_aviso("El usuario ya no existe.")
    try:
        usuario = ServicioUsuarios.cambiar_estado(
            usuario, not usuario.activo, solicitante=request.user
        )
    except ValidationError as error:
        return respuesta_aviso(" ".join(error.messages))
    estado = "activado" if usuario.activo else "desactivado"
    return respuesta_exito(f"Usuario {usuario.username} {estado}.")


@requiere_permiso("usuario.gestionar")
@require_http_methods(["POST"])
def usuario_eliminar(request: HttpRequest, usuario_id: int) -> HttpResponse:
    """Elimina un usuario sin movimientos registrados."""
    usuario = ServicioUsuarios.obtener(usuario_id)
    if usuario is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        username = usuario.username
        ServicioUsuarios.eliminar(usuario, solicitante=request.user)
    except ValidationError as error:
        return respuesta_aviso(" ".join(error.messages))
    return respuesta_exito(f"Usuario {username} eliminado.")


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------
@requiere_permiso("usuario.gestionar")
def roles(request: HttpRequest) -> HttpResponse:
    """Listado de roles con la cantidad de usuarios de cada uno."""
    busqueda = request.GET.get("busqueda", "").strip()
    consulta = ordenar(ServicioRoles.listar(busqueda=busqueda), request, PERMITIDAS_ROL)
    contexto = {
        "titulo": "Roles y permisos",
        "migas": [{"texto": "Administración"}, {"texto": "Roles y permisos"}],
        "busqueda": busqueda,
        "columnas_rol": COLUMNAS_ROL,
        "fichas_filtro": fichas_de_filtro(request, {"busqueda": "Busca"}),
        **paginar(request, consulta),
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

    consulta = ordenar(
        ServicioAuditoria.listar(entidad=entidad, accion=accion, busqueda=busqueda),
        request,
        PERMITIDAS_AUDITORIA,
    )
    contexto = {
        "titulo": "Auditoría",
        "migas": [{"texto": "Administración"}, {"texto": "Auditoría"}],
        "entidad": entidad,
        "accion": accion,
        "busqueda": busqueda,
        "entidades": ServicioAuditoria.entidades(),
        "acciones": RegistroAuditoria.Accion.choices,
        "columnas_auditoria": COLUMNAS_AUDITORIA,
        "fichas_filtro": fichas_de_filtro(
            request,
            {"busqueda": "Busca", "entidad": "Entidad", "accion": "Acción"},
            {"accion": dict(RegistroAuditoria.Accion.choices)},
        ),
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


# ---------------------------------------------------------------------------
# Reinicio de datos de demostración
#
# Sin entrada en ningún menú (navegacion.py): solo se llega escribiendo la
# URL a mano. El permiso «sistema.reiniciar_demo» solo lo trae de fábrica el
# rol oculto Superadministrador (fixture permisos_roles.json), que tampoco
# aparece en el selector de «Nuevo usuario» ni en el listado de roles.
# ---------------------------------------------------------------------------
@requiere_permiso("sistema.reiniciar_demo")
@require_http_methods(["GET", "POST"])
def reiniciar_demo(request: HttpRequest) -> HttpResponse:
    """Borra el catálogo y los movimientos, y vuelve a sembrar la demo."""
    hecho = False
    if request.method == "POST":
        formulario = FormularioReiniciarDemo(request.POST)
        if formulario.is_valid():
            # Importación diferida: evita cargar el comando de siembra en
            # cada arranque del proceso, solo cuando de verdad se usa.
            from django.core.management import call_command  # pylint: disable=import-outside-toplevel

            call_command("reiniciar_demo")
            ServicioAuditoria.registrar(
                entidad="Sistema",
                accion=RegistroAuditoria.Accion.EDITAR,
                detalle={"accion_dominio": "reiniciar_demo"},
            )
            hecho = True
            formulario = FormularioReiniciarDemo()
    else:
        formulario = FormularioReiniciarDemo()

    return render(
        request,
        "nucleo/reiniciar_demo.html",
        {"titulo": "Reiniciar datos de demostración", "formulario": formulario, "hecho": hecho},
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
