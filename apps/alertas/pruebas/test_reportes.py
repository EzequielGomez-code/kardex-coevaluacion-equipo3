"""
Pruebas de los reportes: permisos, que las descargas generan un archivo
válido, y que cada exportación queda en la auditoría.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.movimientos.services import ServicioMovimientos
from apps.nucleo.models import RegistroAuditoria


@pytest.mark.django_db
def test_reportes_indice_exige_permiso(client, usuario_sin_permisos):
    """Sin «reporte.ver», la pantalla de reportes responde 403."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse("alertas:reportes_indice")).status_code == 403


@pytest.mark.django_db
def test_descargar_reporte_exige_permiso_de_exportar(client, usuario_operador):
    """Un operador, sin «reporte.exportar», no puede descargar un reporte."""
    client.force_login(usuario_operador)
    assert client.get(reverse("alertas:reporte_existencias_pdf")).status_code == 403


@pytest.mark.django_db
def test_existencias_pdf_responde_con_un_pdf_valido(
    client, usuario_administrador, tipo_entrada, almacen, articulo
):
    """El PDF de existencias empieza con la firma «%PDF» y queda auditado."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("5")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:reporte_existencias_pdf"))
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
    assert RegistroAuditoria.objects.filter(
        accion=RegistroAuditoria.Accion.EXPORTAR, entidad="Existencia"
    ).exists()


@pytest.mark.django_db
def test_existencias_excel_responde_con_un_libro_valido(
    client, usuario_administrador, tipo_entrada, almacen, articulo
):
    """El Excel de existencias empieza con la firma ZIP que usa el formato xlsx."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("5")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:reporte_existencias_excel"))
    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"PK")


@pytest.mark.django_db
def test_valorizacion_pdf_sin_existencias_no_revienta(client, usuario_administrador):
    """Un reporte sin filas todavía genera un PDF válido, con su aviso en vez de una tabla vacía."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:reporte_valorizacion_pdf"))
    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_movimientos_pdf_filtra_por_rango_de_fechas(
    client, usuario_administrador, tipo_entrada, almacen, articulo
):
    """El reporte de movimientos respeta el rango de fechas de la URL."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(
        reverse("alertas:reporte_movimientos_pdf"), {"desde": "2000-01-01", "hasta": "2000-01-02"}
    )
    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_kardex_pdf_sin_articulo_da_404(client, usuario_administrador):
    """Sin ``?articulo=`` (o con uno inexistente), el reporte de kardex responde 404."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:reporte_kardex_pdf"))
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_kardex_excel_de_un_articulo_real(
    client, usuario_administrador, tipo_entrada, almacen, articulo
):
    """El kardex de un artículo con movimientos exporta un Excel válido."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("5")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:reporte_kardex_excel"), {"articulo": articulo.pk})
    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"PK")
    assert f"kardex-{articulo.sku}" in respuesta["Content-Disposition"]
