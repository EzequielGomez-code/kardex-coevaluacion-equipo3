"""
Vistas de Movimientos.

Cada vista comprueba su permiso en el servidor con ``@requiere_permiso``
(Seguridad #4) y delega en un servicio. Ninguna vista consulta el ORM
directamente.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.catalogo.models import Cliente, Proveedor
from apps.catalogo.repositories import RepositorioArticulos
from apps.movimientos.forms import (
    FormsetLineaAjuste,
    FormsetLineaEntrada,
    FormsetLineaSalida,
    FormsetLineaTransferencia,
    FormularioAjusteCabecera,
    FormularioAnulacion,
    FormularioEntradaCabecera,
    FormularioRechazo,
    FormularioSalidaCabecera,
    FormularioTipoMovimiento,
    FormularioTransferenciaCabecera,
)
from apps.movimientos.models import EstadoMovimiento, Naturaleza
from apps.movimientos.repositories import RepositorioExistencias, RepositorioTiposMovimiento
from apps.movimientos.services import ServicioAprobaciones, ServicioMovimientos, ServicioTiposMovimiento
from apps.nucleo.decoradores import requiere_permiso
from apps.nucleo.repositories import RepositorioAlmacenes
from apps.nucleo.utilidades import (
    entero_o_none,
    fichas_de_filtro,
    ordenar,
    paginar,
    respuesta_aviso,
    respuesta_exito,
)

ETIQUETAS_ESTADO = {
    EstadoMovimiento.BORRADOR: "Borrador", EstadoMovimiento.PENDIENTE: "Pendiente",
    EstadoMovimiento.CONFIRMADO: "Confirmado", EstadoMovimiento.RECHAZADO: "Rechazado",
    EstadoMovimiento.ANULADO: "Anulado",
}
VARIANTES_ESTADO = {
    EstadoMovimiento.BORRADOR: "neutro", EstadoMovimiento.PENDIENTE: "aviso",
    EstadoMovimiento.CONFIRMADO: "ok", EstadoMovimiento.RECHAZADO: "alerta",
    EstadoMovimiento.ANULADO: "neutro",
}
PERMITIDAS_MOVIMIENTO = {
    "numero": "numero", "fecha": "fecha", "estado": "estado", "tipo": "tipo__nombre",
}


def _volcar_errores(formulario, error: ValidationError) -> None:
    """Traslada los errores de un servicio a los campos de un formulario."""
    if hasattr(error, "error_dict"):
        for campo, errores in error.message_dict.items():
            destino = campo if campo in formulario.fields else None
            for mensaje in errores:
                formulario.add_error(destino, mensaje)
    else:
        for mensaje in error.messages:
            formulario.add_error(None, mensaje)


@requiere_permiso("movimiento.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """Listado de movimientos, con filtros por tipo, almacén y estado."""
    busqueda = request.GET.get("busqueda", "").strip()
    tipo_id = entero_o_none(request.GET.get("tipo"))
    almacen_id = entero_o_none(request.GET.get("almacen"))
    estado = request.GET.get("estado", "").strip()

    consulta = ServicioMovimientos.listar(
        busqueda=busqueda, tipo_id=tipo_id, almacen_id=almacen_id, estado=estado
    )
    consulta = ordenar(consulta, request, PERMITIDAS_MOVIMIENTO)

    contexto = {
        "titulo": "Movimientos",
        "migas": [{"texto": "Inventario"}, {"texto": "Movimientos"}],
        "busqueda": busqueda, "tipo_id": tipo_id, "almacen_id": almacen_id, "estado": estado,
        "tipos": RepositorioTiposMovimiento.listar(solo_activos=True),
        "almacenes": RepositorioAlmacenes.activos(),
        "estados": EstadoMovimiento.choices,
        "columnas_movimiento": [
            {"etiqueta": "Número", "clave": "numero"}, {"etiqueta": "Tipo", "clave": "tipo"},
            {"etiqueta": "Fecha", "clave": "fecha"}, {"etiqueta": "Almacén"},
            {"etiqueta": "Cantidad", "clase": "num"}, {"etiqueta": "Costo", "clase": "num"},
            {"etiqueta": "Estado", "clave": "estado"},
        ],
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "tipo": "Tipo", "almacen": "Almacén", "estado": "Estado"},
            {"estado": ETIQUETAS_ESTADO},
        ),
        "etiquetas_estado": ETIQUETAS_ESTADO, "variantes_estado": VARIANTES_ESTADO,
        **paginar(request, consulta),
    }
    return render(request, "movimientos/indice.html", contexto)


@requiere_permiso("movimiento.ver")
def movimiento_detalle(request: HttpRequest, movimiento_id: int) -> HttpResponse:
    """Ficha de un movimiento: cabecera, líneas y, si aplica, su contrapartida."""
    movimiento = ServicioMovimientos.obtener(movimiento_id)
    if movimiento is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    contexto = {
        "titulo": movimiento.numero,
        "migas": [{"texto": "Inventario"}, {"texto": "Movimientos", "destino": reverse("movimientos:indice")},
                 {"texto": movimiento.numero}],
        "movimiento": movimiento,
        "lineas": movimiento.lineas.select_related("articulo", "almacen").order_by("id"),
        "etiquetas_estado": ETIQUETAS_ESTADO, "variantes_estado": VARIANTES_ESTADO,
    }
    return render(request, "movimientos/movimiento_detalle.html", contexto)


@requiere_permiso("movimiento.anular")
@require_http_methods(["GET", "POST"])
def movimiento_anular(request: HttpRequest, movimiento_id: int) -> HttpResponse:
    """Anula un movimiento confirmado mediante su contrapartida."""
    movimiento = ServicioMovimientos.obtener(movimiento_id)
    if movimiento is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioAnulacion(request.POST)
        if formulario.is_valid():
            try:
                ServicioMovimientos.anular(
                    movimiento, formulario.cleaned_data["motivo_anulacion"], request.user
                )
                # HX-Redirect en vez de respuesta_exito: esta pantalla es la
                # ficha de un solo movimiento, no una lista con «region-tabla»
                # escuchando «kardexRecargar» — hace falta la página entera de
                # nuevo para que el estado, el botón y la contrapartida se vean.
                respuesta = HttpResponse(status=204)
                respuesta["HX-Redirect"] = reverse("movimientos:detalle", args=[movimiento.pk])
                return respuesta
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioAnulacion()

    contexto = {
        "formulario": formulario, "movimiento": movimiento,
        "titulo_modal": f"Anular {movimiento.numero}",
        "destino": reverse("movimientos:anular", args=[movimiento.pk]),
        "etiqueta_envio": "Anular movimiento",
    }
    return render(request, "movimientos/movimiento_anular.html", contexto)


@requiere_permiso("movimiento.ver")
def existencias(request: HttpRequest) -> HttpResponse:
    """Existencias por artículo y almacén, con alerta de mínimo."""
    busqueda = request.GET.get("busqueda", "").strip()
    almacen_id = entero_o_none(request.GET.get("almacen"))
    solo_bajo_minimo = request.GET.get("bajo_minimo") == "1"

    consulta = RepositorioExistencias.listar(
        busqueda=busqueda, almacen_id=almacen_id, solo_bajo_minimo=solo_bajo_minimo
    )
    contexto = {
        "titulo": "Existencias",
        "migas": [{"texto": "Inventario"}, {"texto": "Existencias"}],
        "busqueda": busqueda, "almacen_id": almacen_id, "solo_bajo_minimo": solo_bajo_minimo,
        "almacenes": RepositorioAlmacenes.activos(),
        "valor_total": RepositorioExistencias.total_valor(),
        "columnas_existencia": [
            {"etiqueta": "Artículo"}, {"etiqueta": "Almacén"}, {"etiqueta": "Cantidad", "clase": "num"},
            {"etiqueta": "Costo promedio", "clase": "num"}, {"etiqueta": "Valor", "clase": "num"},
            {"etiqueta": "Mínimo", "clase": "num"}, {"etiqueta": "Estado"},
        ],
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "almacen": "Almacén"},
        ),
        **paginar(request, consulta),
    }
    return render(request, "movimientos/existencias.html", contexto)


@requiere_permiso("movimiento.ver")
def kardex(request: HttpRequest, articulo_id: int) -> HttpResponse:
    """Historial cronológico de un artículo: cantidad, costo y saldo corrido."""
    articulo = RepositorioArticulos.obtener(articulo_id)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    almacen_id = entero_o_none(request.GET.get("almacen"))
    consulta = ServicioMovimientos.kardex_de(articulo_id, almacen_id)

    contexto = {
        "titulo": f"Kardex — {articulo.nombre}",
        "migas": [{"texto": "Inventario"}, {"texto": "Movimientos", "destino": reverse("movimientos:indice")},
                 {"texto": f"Kardex de {articulo.sku}"}],
        "articulo": articulo, "almacen_id": almacen_id,
        "almacenes": RepositorioAlmacenes.activos(),
        "existencias": RepositorioExistencias.de_articulo(articulo_id),
        "columnas_kardex": [
            {"etiqueta": "Fecha"}, {"etiqueta": "Movimiento"}, {"etiqueta": "Almacén"},
            {"etiqueta": "Cantidad", "clase": "num"}, {"etiqueta": "Costo unitario", "clase": "num"},
            {"etiqueta": "Saldo", "clase": "num"},
        ],
        **paginar(request, consulta),
    }
    return render(request, "movimientos/kardex.html", contexto)


@requiere_permiso("movimiento.aprobar")
def aprobaciones(request: HttpRequest) -> HttpResponse:
    """Bandeja de movimientos pendientes de aprobación."""
    contexto = {
        "titulo": "Aprobaciones pendientes",
        "migas": [{"texto": "Inventario"}, {"texto": "Aprobaciones"}],
        "movimientos": ServicioAprobaciones.pendientes(),
        "columnas_aprobacion": [
            {"etiqueta": "Número"}, {"etiqueta": "Tipo"}, {"etiqueta": "Fecha"},
            {"etiqueta": "Solicitado por"},
        ],
    }
    return render(request, "movimientos/aprobaciones.html", contexto)


@requiere_permiso("movimiento.aprobar")
@require_http_methods(["POST"])
def movimiento_aprobar(request: HttpRequest, movimiento_id: int) -> HttpResponse:
    """Aprueba un movimiento pendiente: recién aquí se aplican sus efectos."""
    movimiento = ServicioMovimientos.obtener(movimiento_id)
    if movimiento is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        ServicioAprobaciones.aprobar(movimiento, request.user)
        # HX-Redirect: se llama tanto desde la bandeja de aprobaciones como
        # desde la ficha del propio movimiento; en los dos casos el destino
        # correcto es la ficha ya confirmada, con sus líneas recién creadas.
        respuesta = HttpResponse(status=204)
        respuesta["HX-Redirect"] = reverse("movimientos:detalle", args=[movimiento.pk])
        return respuesta
    except ValidationError as error:
        return respuesta_aviso("; ".join(error.messages))


@requiere_permiso("movimiento.aprobar")
@require_http_methods(["GET", "POST"])
def movimiento_rechazar(request: HttpRequest, movimiento_id: int) -> HttpResponse:
    """Rechaza un movimiento pendiente sin tocar el inventario."""
    movimiento = ServicioMovimientos.obtener(movimiento_id)
    if movimiento is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioRechazo(request.POST)
        if formulario.is_valid():
            try:
                ServicioAprobaciones.rechazar(
                    movimiento, formulario.cleaned_data["motivo"], request.user
                )
                respuesta = HttpResponse(status=204)
                respuesta["HX-Redirect"] = reverse("movimientos:detalle", args=[movimiento.pk])
                return respuesta
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioRechazo()

    contexto = {
        "formulario": formulario, "movimiento": movimiento,
        "titulo_modal": f"Rechazar {movimiento.numero}",
        "destino": reverse("movimientos:rechazar", args=[movimiento.pk]),
        "etiqueta_envio": "Rechazar movimiento",
    }
    return render(request, "movimientos/movimiento_rechazar.html", contexto)


def _articulos_disponibles():
    """Artículos activos para el selector con búsqueda de las líneas."""
    return RepositorioArticulos.listar(estado="activo")


@requiere_permiso("movimiento.crear")
@require_http_methods(["GET", "POST"])
def entrada_formulario(request: HttpRequest) -> HttpResponse:
    """Registra una entrada: cada línea crea su propio lote."""
    if request.method == "POST":
        cabecera = FormularioEntradaCabecera(request.POST)
        formset = FormsetLineaEntrada(request.POST)
        if cabecera.is_valid() and formset.is_valid():
            lineas = [
                {
                    "articulo_id": datos["articulo"].pk, "cantidad": datos["cantidad"],
                    "costo_unitario": datos["costo_unitario"],
                    "numero_lote": datos.get("numero_lote", ""),
                    "fecha_vencimiento": datos.get("fecha_vencimiento"),
                }
                for datos in formset.cleaned_data if datos.get("articulo")
            ]
            try:
                movimiento = ServicioMovimientos.registrar_entrada(
                    tipo=cabecera.cleaned_data["tipo"],
                    almacen_destino=cabecera.cleaned_data["almacen_destino"],
                    usuario=request.user, lineas=lineas, fecha=cabecera.cleaned_data.get("fecha"),
                    proveedor=cabecera.cleaned_data.get("proveedor"),
                    documento_tipo=cabecera.cleaned_data.get("documento_tipo", ""),
                    documento_numero=cabecera.cleaned_data.get("documento_numero", ""),
                    ncf=cabecera.cleaned_data.get("ncf", ""),
                    fecha_documento=cabecera.cleaned_data.get("fecha_documento"),
                    motivo=cabecera.cleaned_data.get("motivo", ""),
                    observaciones=cabecera.cleaned_data.get("observaciones", ""),
                )
                mensaje = (
                    f"Entrada «{movimiento.numero}» registrada."
                    if movimiento.estado != EstadoMovimiento.PENDIENTE
                    else f"Entrada «{movimiento.numero}» enviada a aprobación."
                )
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(cabecera, error)
    else:
        cabecera = FormularioEntradaCabecera()
        formset = FormsetLineaEntrada()

    contexto = {
        "cabecera": cabecera, "formset": formset,
        "articulos_disponibles": _articulos_disponibles(),
        "proveedores_disponibles": Proveedor.objects.filter(activo=True).order_by("razon_social"),
        "ancho": True, "titulo_modal": "Nueva entrada", "destino": reverse("movimientos:entrada_nueva"),
        "etiqueta_envio": "Registrar entrada",
    }
    return render(request, "movimientos/entrada_formulario.html", contexto)


@requiere_permiso("movimiento.crear")
@require_http_methods(["GET", "POST"])
def salida_formulario(request: HttpRequest) -> HttpResponse:
    """Registra una salida: consume lotes según el método de valoración vigente."""
    if request.method == "POST":
        cabecera = FormularioSalidaCabecera(request.POST)
        formset = FormsetLineaSalida(request.POST)
        if cabecera.is_valid() and formset.is_valid():
            lineas = [
                {"articulo_id": datos["articulo"].pk, "cantidad": datos["cantidad"]}
                for datos in formset.cleaned_data if datos.get("articulo")
            ]
            try:
                movimiento = ServicioMovimientos.registrar_salida(
                    tipo=cabecera.cleaned_data["tipo"],
                    almacen_origen=cabecera.cleaned_data["almacen_origen"],
                    usuario=request.user, lineas=lineas, fecha=cabecera.cleaned_data.get("fecha"),
                    cliente=cabecera.cleaned_data.get("cliente"),
                    documento_tipo=cabecera.cleaned_data.get("documento_tipo", ""),
                    documento_numero=cabecera.cleaned_data.get("documento_numero", ""),
                    motivo=cabecera.cleaned_data.get("motivo", ""),
                    observaciones=cabecera.cleaned_data.get("observaciones", ""),
                )
                mensaje = (
                    f"Salida «{movimiento.numero}» registrada."
                    if movimiento.estado != EstadoMovimiento.PENDIENTE
                    else f"Salida «{movimiento.numero}» enviada a aprobación."
                )
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(cabecera, error)
    else:
        cabecera = FormularioSalidaCabecera()
        formset = FormsetLineaSalida()

    contexto = {
        "cabecera": cabecera, "formset": formset,
        "articulos_disponibles": _articulos_disponibles(),
        "clientes_disponibles": Cliente.objects.filter(activo=True).order_by("razon_social"),
        "ancho": True, "titulo_modal": "Nueva salida", "destino": reverse("movimientos:salida_nueva"),
        "etiqueta_envio": "Registrar salida",
    }
    return render(request, "movimientos/salida_formulario.html", contexto)


@requiere_permiso("movimiento.crear")
@require_http_methods(["GET", "POST"])
def transferencia_formulario(request: HttpRequest) -> HttpResponse:
    """Registra una transferencia entre almacenes, conservando el costo del lote de origen."""
    if request.method == "POST":
        cabecera = FormularioTransferenciaCabecera(request.POST)
        formset = FormsetLineaTransferencia(request.POST)
        if cabecera.is_valid() and formset.is_valid():
            lineas = [
                {"articulo_id": datos["articulo"].pk, "cantidad": datos["cantidad"]}
                for datos in formset.cleaned_data if datos.get("articulo")
            ]
            try:
                movimiento = ServicioMovimientos.registrar_transferencia(
                    tipo=cabecera.cleaned_data["tipo"],
                    almacen_origen=cabecera.cleaned_data["almacen_origen"],
                    almacen_destino=cabecera.cleaned_data["almacen_destino"],
                    usuario=request.user, lineas=lineas, fecha=cabecera.cleaned_data.get("fecha"),
                    motivo=cabecera.cleaned_data.get("motivo", ""),
                    observaciones=cabecera.cleaned_data.get("observaciones", ""),
                )
                mensaje = (
                    f"Transferencia «{movimiento.numero}» registrada."
                    if movimiento.estado != EstadoMovimiento.PENDIENTE
                    else f"Transferencia «{movimiento.numero}» enviada a aprobación."
                )
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(cabecera, error)
    else:
        cabecera = FormularioTransferenciaCabecera()
        formset = FormsetLineaTransferencia()

    contexto = {
        "cabecera": cabecera, "formset": formset,
        "articulos_disponibles": _articulos_disponibles(),
        "ancho": True, "titulo_modal": "Nueva transferencia",
        "destino": reverse("movimientos:transferencia_nueva"),
        "etiqueta_envio": "Registrar transferencia",
    }
    return render(request, "movimientos/transferencia_formulario.html", contexto)


@requiere_permiso("movimiento.ajustar")
@require_http_methods(["GET", "POST"])
def ajuste_formulario(request: HttpRequest) -> HttpResponse:
    """Registra un ajuste de inventario, con motivo obligatorio."""
    if request.method == "POST":
        cabecera = FormularioAjusteCabecera(request.POST)
        formset = FormsetLineaAjuste(request.POST)
        if cabecera.is_valid() and formset.is_valid():
            lineas = [
                {
                    "articulo_id": datos["articulo"].pk, "cantidad": datos["cantidad"],
                    "signo": datos.get("signo", -1), "costo_unitario": datos.get("costo_unitario"),
                }
                for datos in formset.cleaned_data if datos.get("articulo")
            ]
            try:
                movimiento = ServicioMovimientos.registrar_ajuste(
                    tipo=cabecera.cleaned_data["tipo"], almacen=cabecera.cleaned_data["almacen"],
                    usuario=request.user, lineas=lineas, motivo=cabecera.cleaned_data["motivo"],
                    fecha=cabecera.cleaned_data.get("fecha"),
                    observaciones=cabecera.cleaned_data.get("observaciones", ""),
                )
                mensaje = (
                    f"Ajuste «{movimiento.numero}» registrado."
                    if movimiento.estado != EstadoMovimiento.PENDIENTE
                    else f"Ajuste «{movimiento.numero}» enviado a aprobación."
                )
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(cabecera, error)
    else:
        cabecera = FormularioAjusteCabecera()
        formset = FormsetLineaAjuste()

    contexto = {
        "cabecera": cabecera, "formset": formset,
        "articulos_disponibles": _articulos_disponibles(),
        "ancho": True, "titulo_modal": "Nuevo ajuste", "destino": reverse("movimientos:ajuste_nuevo"),
        "etiqueta_envio": "Registrar ajuste",
    }
    return render(request, "movimientos/ajuste_formulario.html", contexto)


@requiere_permiso("tipo_movimiento.gestionar")
def tipos_lista(request: HttpRequest) -> HttpResponse:
    """Listado de tipos de movimiento configurables."""
    contexto = {
        "titulo": "Tipos de movimiento",
        "migas": [{"texto": "Inventario"}, {"texto": "Movimientos", "destino": reverse("movimientos:indice")},
                 {"texto": "Tipos"}],
        "tipos": ServicioTiposMovimiento.listar(),
        "naturalezas": Naturaleza.choices,
        "columnas_tipo": [
            {"etiqueta": "Código"}, {"etiqueta": "Nombre"}, {"etiqueta": "Naturaleza"},
            {"etiqueta": "Prefijo"}, {"etiqueta": "Aprobación"}, {"etiqueta": "Estado"},
        ],
    }
    return render(request, "movimientos/tipos.html", contexto)


@requiere_permiso("tipo_movimiento.gestionar")
@require_http_methods(["GET", "POST"])
def tipo_formulario(request: HttpRequest, tipo_id: int | None = None) -> HttpResponse:
    """Alta o edición de un tipo de movimiento."""
    tipo = ServicioTiposMovimiento.obtener(tipo_id) if tipo_id else None
    if tipo_id and tipo is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioTipoMovimiento(request.POST, es_edicion=bool(tipo))
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if tipo:
                    datos.pop("codigo", None)
                    datos.pop("naturaleza", None)
                    guardado = ServicioTiposMovimiento.actualizar(tipo, **datos)
                    mensaje = f"Tipo «{guardado.nombre}» actualizado."
                else:
                    guardado = ServicioTiposMovimiento.crear(**datos)
                    mensaje = f"Tipo «{guardado.nombre}» creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if tipo:
            inicial = {
                "codigo": tipo.codigo, "nombre": tipo.nombre, "naturaleza": tipo.naturaleza,
                "prefijo_numeracion": tipo.prefijo_numeracion, "exige_documento": tipo.exige_documento,
                "exige_ncf": tipo.exige_ncf, "exige_motivo": tipo.exige_motivo,
                "exige_aprobacion": tipo.exige_aprobacion, "permite_anulacion": tipo.permite_anulacion,
                "tipo_contrapartida": tipo.tipo_contrapartida_id, "color": tipo.color,
                "orden": tipo.orden, "activo": tipo.activo,
            }
        formulario = FormularioTipoMovimiento(initial=inicial, es_edicion=bool(tipo))

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar tipo de movimiento" if tipo else "Nuevo tipo de movimiento",
        "destino": (
            reverse("movimientos:tipo_editar", args=[tipo.pk]) if tipo
            else reverse("movimientos:tipo_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if tipo else "Crear tipo",
    }
    return render(request, "movimientos/tipo_formulario.html", contexto)
