"""
Vistas de Reportes: la pantalla de menú y las descargas en PDF y Excel.

Ver un reporte y descargarlo son permisos distintos a propósito
(``reporte.ver`` ≠ ``reporte.exportar``): ver no es exfiltrar. Cada descarga
deja su rastro en la auditoría con ``RegistroAuditoria.Accion.EXPORTAR``.
"""

from __future__ import annotations

import datetime as dt

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.alertas.reportes import datos as datos_reporte
from apps.alertas.reportes.excel import construir_excel
from apps.alertas.reportes.pdf import construir_pdf
from apps.catalogo.models import Articulo
from apps.movimientos.repositories import RepositorioTiposMovimiento
from apps.nucleo.decoradores import requiere_permiso
from apps.nucleo.models import Almacen, RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria
from apps.nucleo.utilidades import entero_o_none

CONTENT_TYPE_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fecha(valor: str | None, fin_de_dia: bool = False) -> dt.datetime | None:
    """
    Convierte ``?desde=aaaa-mm-dd`` al inicio (o, con ``fin_de_dia``, al
    final) de ese día, ya con zona horaria — sin esto, Django compara una
    fecha ingenua contra un campo con hora y avisa en cada consulta.
    """
    if not valor:
        return None
    try:
        fecha = dt.date.fromisoformat(valor)
        hora = dt.time.max if fin_de_dia else dt.time.min
        return timezone.make_aware(dt.datetime.combine(fecha, hora))
    except ValueError:
        return None


def _responder_pdf(nombre_archivo: str, titulo: str, filtros: list[str],
                   encabezados: list[str], filas: list[list[str]]) -> HttpResponse:
    contenido = construir_pdf(titulo, filtros, encabezados, filas)
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.pdf"'
    return respuesta


def _responder_excel(nombre_archivo: str, titulo: str,
                     encabezados: list[str], filas: list[list[str]]) -> HttpResponse:
    contenido = construir_excel(titulo, encabezados, filas)
    respuesta = HttpResponse(contenido, content_type=CONTENT_TYPE_EXCEL)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.xlsx"'
    return respuesta


def _auditar_exportacion(entidad: str, detalle: dict) -> None:
    ServicioAuditoria.registrar(
        entidad=entidad, accion=RegistroAuditoria.Accion.EXPORTAR, detalle=detalle,
    )


@requiere_permiso("reporte.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """Menú de los cuatro reportes exportables."""
    contexto = {
        "titulo": "Reportes",
        "migas": [{"texto": "Reportes"}],
        "almacenes": Almacen.objects.filter(activo=True).order_by("codigo"),
        "tipos_movimiento": RepositorioTiposMovimiento.listar(solo_activos=True),
        "articulos": Articulo.objects.filter(activo=True).order_by("nombre")[:200],
    }
    return render(request, "alertas/reportes_indice.html", contexto)


@requiere_permiso("reporte.exportar")
def existencias_pdf(request: HttpRequest) -> HttpResponse:
    """Descarga el reporte de existencias en PDF."""
    busqueda = request.GET.get("busqueda", "")
    almacen_id = entero_o_none(request.GET.get("almacen"))
    encabezados, filas = datos_reporte.existencias(busqueda=busqueda, almacen_id=almacen_id)
    filtros = []
    if almacen_id:
        codigo = Almacen.objects.filter(pk=almacen_id).values_list("codigo", flat=True).first()
        if codigo:
            filtros.append(f"Almacén: {codigo}")
    _auditar_exportacion("Existencia", {"formato": "pdf", "filas": len(filas)})
    return _responder_pdf("existencias", "Existencias", filtros, encabezados, filas)


@requiere_permiso("reporte.exportar")
def existencias_excel(request: HttpRequest) -> HttpResponse:
    """Descarga el reporte de existencias en Excel."""
    busqueda = request.GET.get("busqueda", "")
    almacen_id = entero_o_none(request.GET.get("almacen"))
    encabezados, filas = datos_reporte.existencias(busqueda=busqueda, almacen_id=almacen_id)
    _auditar_exportacion("Existencia", {"formato": "excel", "filas": len(filas)})
    return _responder_excel("existencias", "Existencias", encabezados, filas)


@requiere_permiso("reporte.exportar")
def valorizacion_pdf(request: HttpRequest) -> HttpResponse:
    """Descarga la valorización del inventario en PDF."""
    encabezados, filas = datos_reporte.valorizacion()
    _auditar_exportacion("Existencia", {"formato": "pdf", "reporte": "valorizacion"})
    return _responder_pdf("valorizacion", "Valorización del inventario", [], encabezados, filas)


@requiere_permiso("reporte.exportar")
def valorizacion_excel(request: HttpRequest) -> HttpResponse:
    """Descarga la valorización del inventario en Excel."""
    encabezados, filas = datos_reporte.valorizacion()
    _auditar_exportacion("Existencia", {"formato": "excel", "reporte": "valorizacion"})
    return _responder_excel("valorizacion", "Valorización del inventario", encabezados, filas)


def _filtros_movimientos(request: HttpRequest) -> tuple[dict, list[str]]:
    desde = _fecha(request.GET.get("desde"))
    hasta = _fecha(request.GET.get("hasta"), fin_de_dia=True)
    tipo_id = entero_o_none(request.GET.get("tipo"))
    almacen_id = entero_o_none(request.GET.get("almacen"))
    frases = []
    if desde:
        frases.append(f"Desde {desde:%d/%m/%Y}")
    if hasta:
        frases.append(f"Hasta {hasta:%d/%m/%Y}")
    if tipo_id:
        nombre = RepositorioTiposMovimiento.obtener(tipo_id)
        if nombre:
            frases.append(f"Tipo: {nombre.nombre}")
    if almacen_id:
        codigo = Almacen.objects.filter(pk=almacen_id).values_list("codigo", flat=True).first()
        if codigo:
            frases.append(f"Almacén: {codigo}")
    return {"desde": desde, "hasta": hasta, "tipo_id": tipo_id, "almacen_id": almacen_id}, frases


@requiere_permiso("reporte.exportar")
def movimientos_pdf(request: HttpRequest) -> HttpResponse:
    """Descarga los movimientos de un rango de fechas en PDF."""
    criterios, filtros = _filtros_movimientos(request)
    encabezados, filas = datos_reporte.movimientos_por_rango(**criterios)
    _auditar_exportacion("Movimiento", {"formato": "pdf", "filas": len(filas)})
    return _responder_pdf("movimientos", "Movimientos", filtros, encabezados, filas)


@requiere_permiso("reporte.exportar")
def movimientos_excel(request: HttpRequest) -> HttpResponse:
    """Descarga los movimientos de un rango de fechas en Excel."""
    criterios, _filtros = _filtros_movimientos(request)
    encabezados, filas = datos_reporte.movimientos_por_rango(**criterios)
    _auditar_exportacion("Movimiento", {"formato": "excel", "filas": len(filas)})
    return _responder_excel("movimientos", "Movimientos", encabezados, filas)


def _articulo_del_reporte(request: HttpRequest) -> Articulo | None:
    """Resuelve el artículo elegido en ``?articulo=`` para el reporte de kardex."""
    articulo_id = entero_o_none(request.GET.get("articulo"))
    return Articulo.objects.filter(pk=articulo_id).first() if articulo_id else None


@requiere_permiso("reporte.exportar")
def kardex_pdf(request: HttpRequest) -> HttpResponse:
    """Descarga el kardex de un artículo en PDF."""
    articulo = _articulo_del_reporte(request)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    almacen_id = entero_o_none(request.GET.get("almacen"))
    encabezados, filas = datos_reporte.kardex_de_articulo(articulo.pk, almacen_id)
    filtros = [f"Artículo: {articulo.sku} — {articulo.nombre}"]
    _auditar_exportacion("Articulo", {"formato": "pdf", "reporte": "kardex", "sku": articulo.sku})
    return _responder_pdf(
        f"kardex-{articulo.sku}", f"Kardex — {articulo.nombre}", filtros, encabezados, filas
    )


@requiere_permiso("reporte.exportar")
def kardex_excel(request: HttpRequest) -> HttpResponse:
    """Descarga el kardex de un artículo en Excel."""
    articulo = _articulo_del_reporte(request)
    if articulo is None:
        return render(request, "componentes/no_encontrado.html", status=404)
    almacen_id = entero_o_none(request.GET.get("almacen"))
    encabezados, filas = datos_reporte.kardex_de_articulo(articulo.pk, almacen_id)
    _auditar_exportacion("Articulo", {"formato": "excel", "reporte": "kardex", "sku": articulo.sku})
    return _responder_excel(f"kardex-{articulo.sku}", f"Kardex — {articulo.nombre}", encabezados, filas)
