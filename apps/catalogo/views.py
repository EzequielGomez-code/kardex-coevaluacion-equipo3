"""
Vistas del catálogo: categorías, marcas, unidades, artículos, proveedores,
clientes y sus precios.

Ninguna vista consulta el ORM: todas pasan por los servicios. Cada vista que
modifica datos comprueba su permiso en el servidor (Seguridad #4).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.catalogo.forms import (
    FormularioArticulo,
    FormularioCategoria,
    FormularioCliente,
    FormularioImportacionArticulos,
    FormularioMarca,
    FormularioPrecioProveedor,
    FormularioProveedor,
    FormularioUnidadMedida,
)
from apps.catalogo.models import Cliente, Proveedor
from apps.catalogo.repositories import RepositorioProveedorArticulo
from apps.catalogo.services import (
    ServicioArticulos,
    ServicioCategorias,
    ServicioClientes,
    ServicioImportacionArticulos,
    ServicioMarcas,
    ServicioProveedores,
    ServicioUnidadesMedida,
)
from apps.configuracion.forms import FormularioCamposDinamicos
from apps.configuracion.services import ServicioCamposPersonalizados
from apps.nucleo.decoradores import requiere_permiso
from apps.nucleo.utilidades import (
    cuerpo_json,
    entero_o_none,
    fichas_de_filtro,
    ordenar,
    paginar,
    respuesta_aviso,
    respuesta_exito,
)

ETIQUETAS_ESTADO = {"activo": "Activos", "inactivo": "Inactivos"}

COLUMNAS_MARCA = [
    {"etiqueta": "Marca", "clave": "nombre"},
    {"etiqueta": "País"},
    {"etiqueta": "Artículos", "clase": "num"},
    {"etiqueta": "Estado"},
]
PERMITIDAS_MARCA = {"nombre": "nombre"}
PERMITIDAS_UNIDAD = {"codigo": "codigo", "nombre": "nombre"}

COLUMNAS_UNIDAD = [
    {"etiqueta": "Código", "clave": "codigo"},
    {"etiqueta": "Nombre", "clave": "nombre"},
    {"etiqueta": "Decimales"},
    {"etiqueta": "Estado"},
]

COLUMNAS_ARTICULO = [
    {"etiqueta": "SKU", "clave": "sku"},
    {"etiqueta": "Nombre", "clave": "nombre"},
    {"etiqueta": "Categoría"},
    {"etiqueta": "Marca"},
    {"etiqueta": "Precio", "clase": "num"},
    {"etiqueta": "Estado"},
]
PERMITIDAS_ARTICULO = {"sku": "sku", "nombre": "nombre"}

COLUMNAS_TERCERO = [
    {"etiqueta": "Código", "clave": "codigo"},
    {"etiqueta": "Razón social", "clave": "razon_social"},
    {"etiqueta": "RNC / Cédula"},
    {"etiqueta": "Teléfono"},
    {"etiqueta": "Estado"},
]
PERMITIDAS_TERCERO = {"codigo": "codigo", "razon_social": "razon_social"}


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
# Categorías
# ---------------------------------------------------------------------------
@requiere_permiso("articulo.ver")
def categorias(request: HttpRequest) -> HttpResponse:
    """Árbol completo de categorías, ya en el orden de pantalla."""
    contexto = {
        "titulo": "Categorías",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Categorías"}],
        "arbol": ServicioCategorias.arbol(),
        "puede_gestionar": request.user.tiene_permiso("categoria.gestionar"),
    }
    return render(request, "catalogo/categorias.html", contexto)


@requiere_permiso("categoria.gestionar")
@require_http_methods(["GET", "POST"])
def categoria_formulario(request: HttpRequest, categoria_id: int | None = None) -> HttpResponse:
    """Alta o edición de una categoría. El padre llega por ``?padre=`` al crear."""
    categoria = ServicioCategorias.obtener(categoria_id) if categoria_id else None
    if categoria_id and categoria is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    padre_id = entero_o_none(request.GET.get("padre")) if not categoria else categoria.padre_id
    padre = ServicioCategorias.obtener(padre_id) if padre_id else None

    if request.method == "POST":
        formulario = FormularioCategoria(request.POST, es_edicion=categoria is not None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if categoria:
                    ServicioCategorias.actualizar(
                        categoria, nombre=datos["nombre"], descripcion=datos["descripcion"],
                        icono=datos["icono"], activo=datos["activo"],
                    )
                    mensaje = f"Categoría «{datos['nombre']}» actualizada."
                else:
                    ServicioCategorias.crear(
                        codigo=datos["codigo"], nombre=datos["nombre"],
                        descripcion=datos["descripcion"], padre=padre, icono=datos["icono"],
                    )
                    mensaje = f"Categoría «{datos['nombre']}» creada."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if categoria:
            inicial = {
                "codigo": categoria.codigo, "nombre": categoria.nombre,
                "descripcion": categoria.descripcion, "icono": categoria.icono,
                "activo": categoria.activo,
            }
        formulario = FormularioCategoria(initial=inicial, es_edicion=categoria is not None)

    if categoria:
        destino = reverse("catalogo:categoria_editar", args=[categoria.pk])
    elif padre:
        destino = f"{reverse('catalogo:categoria_nueva')}?padre={padre.pk}"
    else:
        destino = reverse("catalogo:categoria_nueva")

    contexto = {
        "formulario": formulario,
        "padre": padre,
        "titulo_modal": "Editar categoría" if categoria else "Nueva categoría",
        "destino": destino,
        "etiqueta_envio": "Guardar cambios" if categoria else "Crear categoría",
    }
    return render(request, "catalogo/categoria_formulario.html", contexto)


@requiere_permiso("categoria.gestionar")
@require_http_methods(["POST"])
def categoria_eliminar(request: HttpRequest, categoria_id: int) -> HttpResponse:
    """Elimina una categoría vacía (sin hijas ni artículos)."""
    categoria = ServicioCategorias.obtener(categoria_id)
    if categoria is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        nombre = categoria.nombre
        ServicioCategorias.eliminar(categoria)
    except ValidationError as error:
        return respuesta_aviso(" ".join(error.messages))
    return respuesta_exito(f"Categoría «{nombre}» eliminada.")


@requiere_permiso("categoria.gestionar")
@require_http_methods(["POST"])
def categorias_reordenar(request: HttpRequest) -> HttpResponse:
    """Recibe el nuevo orden entre hermanas tras arrastrarlas. Cuerpo JSON."""
    cuerpo = cuerpo_json(request)
    if cuerpo is None:
        return JsonResponse({"error": "Orden inválido."}, status=400)
    try:
        padre_id = entero_o_none(cuerpo.get("padre_id"))
        identificadores = [int(valor) for valor in cuerpo.get("orden", [])]
    except (ValueError, TypeError):
        return JsonResponse({"error": "Orden inválido."}, status=400)

    if not identificadores:
        return JsonResponse({"error": "No se recibió ninguna categoría."}, status=400)

    try:
        ServicioCategorias.reordenar(padre_id, identificadores)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({"guardado": True, "total": len(identificadores)})


@requiere_permiso("categoria.gestionar")
@require_http_methods(["POST"])
def categorias_mover(request: HttpRequest) -> HttpResponse:
    """Mueve una categoría (con su subárbol) a otro padre. Cuerpo JSON."""
    cuerpo = cuerpo_json(request)
    if cuerpo is None:
        return JsonResponse({"error": "Solicitud inválida."}, status=400)
    try:
        categoria_id = int(cuerpo["categoria_id"])
        nuevo_padre_id = entero_o_none(cuerpo.get("nuevo_padre_id"))
    except (ValueError, TypeError, KeyError):
        return JsonResponse({"error": "Solicitud inválida."}, status=400)

    categoria = ServicioCategorias.obtener(categoria_id)
    if categoria is None:
        return JsonResponse({"error": "La categoría ya no existe."}, status=404)
    nuevo_padre = ServicioCategorias.obtener(nuevo_padre_id) if nuevo_padre_id else None

    try:
        ServicioCategorias.mover(categoria, nuevo_padre)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({"movido": True})


# ---------------------------------------------------------------------------
# Marcas
# ---------------------------------------------------------------------------
@requiere_permiso("articulo.ver")
def marcas(request: HttpRequest) -> HttpResponse:
    """Listado de marcas."""
    busqueda = request.GET.get("busqueda", "").strip()
    consulta = ServicioMarcas.listar()
    if busqueda:
        consulta = consulta.filter(nombre__icontains=busqueda)
    consulta = ordenar(consulta, request, PERMITIDAS_MARCA)
    contexto = {
        "titulo": "Marcas",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Marcas"}],
        "busqueda": busqueda,
        "columnas_marca": COLUMNAS_MARCA,
        "fichas_filtro": fichas_de_filtro(request, {"busqueda": "Busca"}),
        **paginar(request, consulta),
    }
    return render(request, "catalogo/marcas.html", contexto)


@requiere_permiso("categoria.gestionar")
@require_http_methods(["GET", "POST"])
def marca_formulario(request: HttpRequest, marca_id: int | None = None) -> HttpResponse:
    """Alta o edición de una marca."""
    marca = ServicioMarcas.obtener(marca_id) if marca_id else None
    if marca_id and marca is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioMarca(request.POST)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            if marca:
                ServicioMarcas.actualizar(marca, **datos)
                mensaje = f"Marca «{datos['nombre']}» actualizada."
            else:
                ServicioMarcas.crear(datos["nombre"], datos["pais"], datos["sitio_web"])
                mensaje = f"Marca «{datos['nombre']}» creada."
            return respuesta_exito(mensaje)
    else:
        inicial = (
            {"nombre": marca.nombre, "pais": marca.pais, "sitio_web": marca.sitio_web,
             "activo": marca.activo}
            if marca else {}
        )
        formulario = FormularioMarca(initial=inicial)

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar marca" if marca else "Nueva marca",
        "destino": (
            reverse("catalogo:marca_editar", args=[marca.pk])
            if marca else reverse("catalogo:marca_nueva")
        ),
        "etiqueta_envio": "Guardar cambios" if marca else "Crear marca",
    }
    return render(request, "catalogo/marca_formulario.html", contexto)


# ---------------------------------------------------------------------------
# Unidades de medida
# ---------------------------------------------------------------------------
@requiere_permiso("articulo.ver")
def unidades(request: HttpRequest) -> HttpResponse:
    """Listado de unidades de medida."""
    consulta = ordenar(ServicioUnidadesMedida.listar(), request, PERMITIDAS_UNIDAD)
    contexto = {
        "titulo": "Unidades de medida",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Unidades"}],
        "columnas_unidad": COLUMNAS_UNIDAD,
        **paginar(request, consulta),
    }
    return render(request, "catalogo/unidades.html", contexto)


@requiere_permiso("categoria.gestionar")
@require_http_methods(["GET", "POST"])
def unidad_formulario(request: HttpRequest, unidad_id: int | None = None) -> HttpResponse:
    """Alta o edición de una unidad de medida."""
    unidad = ServicioUnidadesMedida.obtener(unidad_id) if unidad_id else None
    if unidad_id and unidad is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioUnidadMedida(request.POST, es_edicion=unidad is not None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            if unidad:
                ServicioUnidadesMedida.actualizar(
                    unidad, datos["nombre"], datos["simbolo"], datos["permite_decimales"],
                    datos["activo"],
                )
                mensaje = f"Unidad «{datos['nombre']}» actualizada."
            else:
                ServicioUnidadesMedida.crear(
                    datos["codigo"], datos["nombre"], datos["simbolo"], datos["permite_decimales"]
                )
                mensaje = f"Unidad «{datos['nombre']}» creada."
            return respuesta_exito(mensaje)
    else:
        inicial = (
            {"codigo": unidad.codigo, "nombre": unidad.nombre, "simbolo": unidad.simbolo,
             "permite_decimales": unidad.permite_decimales, "activo": unidad.activo}
            if unidad else {}
        )
        formulario = FormularioUnidadMedida(initial=inicial, es_edicion=unidad is not None)

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar unidad" if unidad else "Nueva unidad de medida",
        "destino": (
            reverse("catalogo:unidad_editar", args=[unidad.pk])
            if unidad else reverse("catalogo:unidad_nueva")
        ),
        "etiqueta_envio": "Guardar cambios" if unidad else "Crear unidad",
    }
    return render(request, "catalogo/unidad_formulario.html", contexto)


@requiere_permiso("categoria.gestionar")
@require_http_methods(["POST"])
def unidad_eliminar(request: HttpRequest, unidad_id: int) -> HttpResponse:
    """Elimina una unidad de medida sin artículos asignados."""
    unidad = ServicioUnidadesMedida.obtener(unidad_id)
    if unidad is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    try:
        nombre = unidad.nombre
        ServicioUnidadesMedida.eliminar(unidad)
    except ValidationError as error:
        return respuesta_aviso(" ".join(error.messages))
    return respuesta_exito(f"Unidad «{nombre}» eliminada.")


# ---------------------------------------------------------------------------
# Artículos
# ---------------------------------------------------------------------------
@requiere_permiso("articulo.ver")
def articulos(request: HttpRequest) -> HttpResponse:
    """Listado de artículos, con filtros en la URL."""
    busqueda = request.GET.get("busqueda", "").strip()
    categoria_id = entero_o_none(request.GET.get("categoria"))
    marca_id = entero_o_none(request.GET.get("marca"))
    estado = request.GET.get("estado", "")

    consulta = ordenar(
        ServicioArticulos.listar(
            busqueda=busqueda, categoria_id=categoria_id, marca_id=marca_id, estado=estado
        ),
        request, PERMITIDAS_ARTICULO,
    )

    categoria_actual = ServicioCategorias.obtener(categoria_id) if categoria_id else None
    marca_actual = ServicioMarcas.obtener(marca_id) if marca_id else None

    contexto = {
        "titulo": "Artículos",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Artículos"}],
        "busqueda": busqueda,
        "categoria_id": categoria_id,
        "marca_id": marca_id,
        "estado": estado,
        "categorias": ServicioCategorias.arbol(solo_activas=True),
        "marcas_disponibles": ServicioMarcas.listar(solo_activas=True),
        "columnas_articulo": COLUMNAS_ARTICULO,
        "fichas_filtro": fichas_de_filtro(
            request,
            {"busqueda": "Busca", "categoria": "Categoría", "marca": "Marca", "estado": "Estado"},
            {
                "categoria": {str(categoria_id): categoria_actual.nombre} if categoria_actual else {},
                "marca": {str(marca_id): marca_actual.nombre} if marca_actual else {},
                "estado": ETIQUETAS_ESTADO,
            },
        ),
        **paginar(request, consulta),
    }
    return render(request, "catalogo/articulos.html", contexto)


@requiere_permiso("articulo.crear", "articulo.editar")
@require_http_methods(["GET", "POST"])
def articulo_formulario(request: HttpRequest, articulo_id: int | None = None) -> HttpResponse:
    """Alta o edición de un artículo, con sus campos personalizados por categoría."""
    articulo = ServicioArticulos.obtener(articulo_id) if articulo_id else None
    if articulo_id and articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    if articulo and not request.user.tiene_permiso("articulo.editar"):
        return render(request, "nucleo/error.html", {"codigo": "403", "titulo": "Acceso denegado",
                     "detalle": "Su rol no tiene permiso para editar artículos."}, status=403)
    if not articulo and not request.user.tiene_permiso("articulo.crear"):
        return render(request, "nucleo/error.html", {"codigo": "403", "titulo": "Acceso denegado",
                     "detalle": "Su rol no tiene permiso para crear artículos."}, status=403)

    categoria_codigo = articulo.categoria.codigo if articulo else request.POST.get("categoria_codigo", "")

    if request.method == "POST":
        formulario = FormularioArticulo(request.POST, request.FILES)
        # La categoría elegida decide qué campos personalizados aplican; se
        # resuelve tras validar el campo «categoria» para tener la instancia.
        categoria_elegida = None
        if formulario.is_valid():
            categoria_elegida = formulario.cleaned_data["categoria"]
        personalizados = FormularioCamposDinamicos(
            request.POST, entidad="Articulo",
            categoria=categoria_elegida.codigo if categoria_elegida else categoria_codigo,
            instancia=articulo,
        )
        if formulario.is_valid() and personalizados.is_valid():
            datos = formulario.cleaned_data
            try:
                if articulo:
                    guardado = ServicioArticulos.actualizar(articulo, **datos)
                    mensaje = f"Artículo «{guardado.nombre}» actualizado."
                else:
                    guardado = ServicioArticulos.crear(**datos)
                    mensaje = f"Artículo «{guardado.nombre}» creado."
                personalizados.guardar(guardado)
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if articulo:
            inicial = {
                "sku": articulo.sku, "codigo_barras": articulo.codigo_barras,
                "nombre": articulo.nombre, "descripcion": articulo.descripcion,
                "categoria": articulo.categoria_id, "marca": articulo.marca_id,
                "unidad": articulo.unidad_id, "es_inventariable": articulo.es_inventariable,
                "maneja_lotes": articulo.maneja_lotes,
                "maneja_vencimiento": articulo.maneja_vencimiento,
                "costo_referencia": articulo.costo_referencia,
                "precio_venta": articulo.precio_venta, "tasa_itbis": articulo.tasa_itbis,
                "stock_minimo_defecto": articulo.stock_minimo_defecto, "activo": articulo.activo,
            }
        formulario = FormularioArticulo(initial=inicial)
        personalizados = FormularioCamposDinamicos(
            entidad="Articulo", categoria=categoria_codigo, instancia=articulo
        )

    contexto = {
        "formulario": formulario,
        "campos_personalizados": personalizados,
        "titulo_modal": "Editar artículo" if articulo else "Nuevo artículo",
        "destino": (
            reverse("catalogo:articulo_editar", args=[articulo.pk])
            if articulo else reverse("catalogo:articulo_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if articulo else "Crear artículo",
    }
    return render(request, "catalogo/articulo_formulario.html", contexto)


@requiere_permiso("articulo.ver")
def articulo_campos_de_categoria(request: HttpRequest) -> HttpResponse:
    """
    Endpoint HTMX: devuelve los campos personalizados de la categoría elegida.

    Se dispara al cambiar el selector de categoría en el formulario de
    artículo, para que los campos se carguen de forma dinámica (criterio del
    BRIEF 02, fase 3).
    """
    categoria_id = entero_o_none(request.GET.get("categoria"))
    categoria = ServicioCategorias.obtener(categoria_id) if categoria_id else None
    personalizados = FormularioCamposDinamicos(
        entidad="Articulo", categoria=categoria.codigo if categoria else ""
    )
    return render(
        request, "catalogo/_campos_dinamicos_articulo.html",
        {"campos_personalizados": personalizados},
    )


@requiere_permiso("articulo.ver")
def articulo_detalle(request: HttpRequest, articulo_id: int) -> HttpResponse:
    """Ficha de un artículo, con pestañas de datos relacionados."""
    articulo = ServicioArticulos.obtener(articulo_id)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    pestana = request.GET.get("pestana", "general")
    contexto = {
        "titulo": articulo.nombre,
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"},
                 {"texto": "Artículos", "destino": reverse("catalogo:articulos")},
                 {"texto": articulo.sku}],
        "articulo": articulo,
        "pestana": pestana,
        "proveedores_articulo": RepositorioProveedorArticulo.de_articulo(articulo),
        "campos_personalizados": ServicioCamposPersonalizados.valores_con_etiqueta(
            articulo, "Articulo", articulo.categoria.codigo
        ),
    }
    return render(request, "catalogo/articulo_detalle.html", contexto)


@requiere_permiso("articulo.eliminar")
@require_http_methods(["POST"])
def articulo_eliminar(request: HttpRequest, articulo_id: int) -> HttpResponse:
    """Da de baja un artículo: borrado duro si nunca tuvo movimientos, si no, lógico."""
    articulo = ServicioArticulos.obtener(articulo_id)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    nombre = articulo.nombre
    ServicioArticulos.dar_de_baja(articulo)
    return respuesta_exito(f"Artículo «{nombre}» dado de baja.")


# ---------------------------------------------------------------------------
# Importación masiva
#
# Entre la vista previa, la confirmación y el reporte de errores no se guarda
# el archivo en el servidor: el mismo <input type="file"> se reenvía en cada
# paso (tres botones «formaction» distintos sobre un único formulario), y
# ServicioImportacionArticulos lo vuelve a leer cada vez.
# ---------------------------------------------------------------------------
@requiere_permiso("importacion.ejecutar")
def articulo_importar(request: HttpRequest) -> HttpResponse:
    """Pantalla de carga masiva: el mapeo de columnas y el archivo."""
    formulario = FormularioImportacionArticulos(
        initial=ServicioImportacionArticulos.mapeo_guardado(request.user)
    )
    contexto = {
        "titulo": "Importar artículos",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo", "destino": reverse("catalogo:articulos")},
                 {"texto": "Importar"}],
        "formulario": formulario,
    }
    return render(request, "catalogo/articulo_importar.html", contexto)


@requiere_permiso("importacion.ejecutar")
@require_http_methods(["POST"])
def articulo_importar_previsualizar(request: HttpRequest) -> HttpResponse:
    """Lee el archivo, valida cada fila y devuelve la tabla de vista previa."""
    formulario = FormularioImportacionArticulos(request.POST, request.FILES)
    if not formulario.is_valid():
        return render(request, "catalogo/_importar_resultado.html", {"formulario": formulario})

    filas = ServicioImportacionArticulos.previsualizar(
        request.FILES["archivo"], formulario.mapeo()
    )
    contexto = {
        "filas": filas[:200],
        "total_filas": len(filas),
        "validas": sum(1 for fila in filas if fila.es_valida),
        "con_error": sum(1 for fila in filas if not fila.es_valida),
        "formulario": formulario,
    }
    return render(request, "catalogo/_importar_resultado.html", contexto)


@requiere_permiso("importacion.ejecutar")
@require_http_methods(["POST"])
def articulo_importar_confirmar(request: HttpRequest) -> HttpResponse:
    """Crea los artículos válidos del archivo y guarda el mapeo para la próxima vez."""
    formulario = FormularioImportacionArticulos(request.POST, request.FILES)
    if not formulario.is_valid():
        return render(request, "catalogo/_importar_resultado.html", {"formulario": formulario})

    creados, con_error, filas = ServicioImportacionArticulos.confirmar(
        request.FILES["archivo"], formulario.mapeo(), request.user
    )
    contexto = {
        "titulo": "Importar artículos",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo", "destino": reverse("catalogo:articulos")},
                 {"texto": "Importar"}],
        "confirmado": True, "creados": creados, "con_error": con_error,
        "filas_con_error": [fila for fila in filas if not fila.es_valida][:200],
    }
    return render(request, "catalogo/articulo_importar_confirmado.html", contexto)


@requiere_permiso("importacion.ejecutar")
@require_http_methods(["POST"])
def articulo_importar_errores(request: HttpRequest) -> HttpResponse:
    """Descarga un CSV con solo las filas que fallaron la validación."""
    formulario = FormularioImportacionArticulos(request.POST, request.FILES)
    if not formulario.is_valid():
        return render(request, "catalogo/_importar_resultado.html", {"formulario": formulario})

    contenido = ServicioImportacionArticulos.reporte_de_errores(
        request.FILES["archivo"], formulario.mapeo()
    )
    respuesta = HttpResponse(contenido, content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="errores_importacion.csv"'
    return respuesta


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------
@requiere_permiso("proveedor.ver")
def proveedores(request: HttpRequest) -> HttpResponse:
    """Listado de proveedores."""
    busqueda = request.GET.get("busqueda", "").strip()
    estado = request.GET.get("estado", "")
    consulta = ordenar(
        ServicioProveedores.listar(busqueda=busqueda, estado=estado), request, PERMITIDAS_TERCERO
    )
    contexto = {
        "titulo": "Proveedores",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Proveedores"}],
        "busqueda": busqueda,
        "estado": estado,
        "columnas_tercero": COLUMNAS_TERCERO,
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "estado": "Estado"}, {"estado": ETIQUETAS_ESTADO}
        ),
        **paginar(request, consulta),
    }
    return render(request, "catalogo/proveedores.html", contexto)


@requiere_permiso("proveedor.gestionar")
@require_http_methods(["GET", "POST"])
def proveedor_formulario(request: HttpRequest, proveedor_id: int | None = None) -> HttpResponse:
    """Alta o edición de un proveedor."""
    proveedor = ServicioProveedores.obtener(proveedor_id) if proveedor_id else None
    if proveedor_id and proveedor is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioProveedor(request.POST, es_edicion=proveedor is not None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if proveedor:
                    ServicioProveedores.actualizar(proveedor, **datos)
                    mensaje = f"Proveedor «{datos['razon_social']}» actualizado."
                else:
                    ServicioProveedores.crear(**datos)
                    mensaje = f"Proveedor «{datos['razon_social']}» creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioProveedor(
            initial=_inicial_tercero(proveedor), es_edicion=proveedor is not None
        )

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar proveedor" if proveedor else "Nuevo proveedor",
        "destino": (
            reverse("catalogo:proveedor_editar", args=[proveedor.pk])
            if proveedor else reverse("catalogo:proveedor_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if proveedor else "Crear proveedor",
    }
    return render(request, "catalogo/proveedor_formulario.html", contexto)


@requiere_permiso("proveedor.gestionar")
@require_http_methods(["POST"])
def proveedor_alternar_estado(request: HttpRequest, proveedor_id: int) -> HttpResponse:
    """Activa o desactiva un proveedor."""
    proveedor = ServicioProveedores.obtener(proveedor_id)
    if proveedor is None:
        return respuesta_aviso("El proveedor ya no existe.")
    proveedor = ServicioProveedores.cambiar_estado(proveedor, not proveedor.activo)
    estado = "activado" if proveedor.activo else "desactivado"
    return respuesta_exito(f"Proveedor «{proveedor.razon_social}» {estado}.")


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
@requiere_permiso("cliente.ver")
def clientes(request: HttpRequest) -> HttpResponse:
    """Listado de clientes."""
    busqueda = request.GET.get("busqueda", "").strip()
    estado = request.GET.get("estado", "")
    consulta = ordenar(
        ServicioClientes.listar(busqueda=busqueda, estado=estado), request, PERMITIDAS_TERCERO
    )
    contexto = {
        "titulo": "Clientes",
        "migas": [{"texto": "Inventario"}, {"texto": "Catálogo"}, {"texto": "Clientes"}],
        "busqueda": busqueda,
        "estado": estado,
        "columnas_tercero": COLUMNAS_TERCERO,
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "estado": "Estado"}, {"estado": ETIQUETAS_ESTADO}
        ),
        **paginar(request, consulta),
    }
    return render(request, "catalogo/clientes.html", contexto)


@requiere_permiso("cliente.gestionar")
@require_http_methods(["GET", "POST"])
def cliente_formulario(request: HttpRequest, cliente_id: int | None = None) -> HttpResponse:
    """Alta o edición de un cliente."""
    cliente = ServicioClientes.obtener(cliente_id) if cliente_id else None
    if cliente_id and cliente is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioCliente(request.POST, es_edicion=cliente is not None)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if cliente:
                    ServicioClientes.actualizar(cliente, **datos)
                    mensaje = f"Cliente «{datos['razon_social']}» actualizado."
                else:
                    ServicioClientes.crear(**datos)
                    mensaje = f"Cliente «{datos['razon_social']}» creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioCliente(
            initial=_inicial_tercero(cliente), es_edicion=cliente is not None
        )

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar cliente" if cliente else "Nuevo cliente",
        "destino": (
            reverse("catalogo:cliente_editar", args=[cliente.pk])
            if cliente else reverse("catalogo:cliente_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if cliente else "Crear cliente",
    }
    return render(request, "catalogo/cliente_formulario.html", contexto)


@requiere_permiso("cliente.gestionar")
@require_http_methods(["POST"])
def cliente_alternar_estado(request: HttpRequest, cliente_id: int) -> HttpResponse:
    """Activa o desactiva un cliente."""
    cliente = ServicioClientes.obtener(cliente_id)
    if cliente is None:
        return respuesta_aviso("El cliente ya no existe.")
    ServicioClientes.cambiar_estado(cliente, not cliente.activo)
    cliente.refresh_from_db()
    estado = "activado" if cliente.activo else "desactivado"
    return respuesta_exito(f"Cliente «{cliente.razon_social}» {estado}.")


def _inicial_tercero(instancia: Proveedor | Cliente | None) -> dict:
    """Arma el diccionario ``initial`` de un formulario de tercero desde su instancia."""
    if not instancia:
        return {}
    return {
        "codigo": instancia.codigo, "razon_social": instancia.razon_social,
        "nombre_comercial": instancia.nombre_comercial,
        "tipo_documento": instancia.tipo_documento, "rnc": instancia.rnc,
        "telefono": instancia.telefono, "email": instancia.email,
        "direccion": instancia.direccion, "contacto": instancia.contacto,
        "dias_credito": instancia.dias_credito, "limite_credito": instancia.limite_credito,
        "notas": instancia.notas, "activo": instancia.activo,
    }


# ---------------------------------------------------------------------------
# Precios de proveedor por artículo
# ---------------------------------------------------------------------------
@requiere_permiso("proveedor.gestionar")
@require_http_methods(["GET", "POST"])
def precio_formulario(
    request: HttpRequest, articulo_id: int | None = None, relacion_id: int | None = None
) -> HttpResponse:
    """Alta (desde un artículo, eligiendo proveedor) o edición de un precio."""
    relacion = RepositorioProveedorArticulo.obtener(relacion_id) if relacion_id else None
    if relacion_id and relacion is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    articulo = relacion.articulo if relacion else ServicioArticulos.obtener(articulo_id)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioPrecioProveedor(request.POST)
        proveedor_id = entero_o_none(request.POST.get("proveedor")) if not relacion else None
        proveedor = relacion.proveedor if relacion else ServicioProveedores.obtener(proveedor_id)

        if proveedor is None:
            formulario.add_error(None, "Seleccione un proveedor.")
        if formulario.is_valid() and proveedor is not None:
            try:
                ServicioProveedores.fijar_precio(proveedor, articulo, **formulario.cleaned_data)
                return respuesta_exito(f"Precio de «{proveedor.razon_social}» guardado.")
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = (
            {"codigo_proveedor": relacion.codigo_proveedor, "precio_compra": relacion.precio_compra,
             "tiempo_entrega_dias": relacion.tiempo_entrega_dias,
             "cantidad_minima": relacion.cantidad_minima, "es_preferido": relacion.es_preferido,
             "activo": relacion.activo}
            if relacion else {}
        )
        formulario = FormularioPrecioProveedor(initial=inicial)

    contexto = {
        "formulario": formulario,
        "articulo": articulo,
        "relacion": relacion,
        "proveedores_disponibles": ServicioProveedores.listar(estado="activo") if not relacion else None,
        "titulo_modal": "Editar precio" if relacion else "Nuevo precio de proveedor",
        "destino": (
            reverse("catalogo:precio_editar", args=[relacion.pk])
            if relacion else reverse("catalogo:precio_nuevo", args=[articulo.pk])
        ),
        "etiqueta_envio": "Guardar cambios" if relacion else "Guardar precio",
    }
    return render(request, "catalogo/precio_formulario.html", contexto)


@requiere_permiso("proveedor.gestionar")
@require_http_methods(["POST"])
def precio_eliminar(request: HttpRequest, relacion_id: int) -> HttpResponse:
    """Elimina la relación de precio entre un proveedor y un artículo."""
    relacion = RepositorioProveedorArticulo.obtener(relacion_id)
    if relacion is None:
        return respuesta_aviso("Ese precio ya no existe.")
    ServicioProveedores.quitar_precio(relacion)
    return respuesta_exito("Precio eliminado.")
