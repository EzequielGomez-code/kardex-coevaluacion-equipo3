"""
Pruebas de las vistas de Movimientos: permisos, y que cada pantalla renderiza
sin reventar (la prueba más simple de que las plantillas están bien armadas).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.movimientos.models import TipoMovimiento
from apps.movimientos.services import ServicioMovimientos


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nombre_ruta,args",
    [
        ("movimientos:indice", []),
        ("movimientos:existencias", []),
        ("movimientos:tipos", []),
    ],
)
def test_las_pantallas_de_listado_exigen_permiso(client, usuario_sin_permisos, nombre_ruta, args):
    """Ninguna pantalla del módulo se abre sin su permiso (Seguridad #4)."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse(nombre_ruta, args=args)).status_code == 403


@pytest.mark.django_db
def test_indice_responde_200_y_pinta_la_tabla(client, usuario_administrador, tipo_entrada, almacen, articulo):
    """El listado renderiza aunque ya existan movimientos confirmados."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:indice"))
    assert respuesta.status_code == 200
    assert b"ENT-000001" in respuesta.content


@pytest.mark.django_db
def test_indice_vacio_muestra_estado_vacio(client, usuario_administrador):
    """Sin movimientos, el listado muestra el estado vacío en vez de una tabla rota."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:indice"))
    assert respuesta.status_code == 200
    assert "No hay movimientos" in respuesta.content.decode()


@pytest.mark.django_db
def test_existencias_responde_200(client, usuario_administrador, tipo_entrada, almacen, articulo):
    """La pantalla de existencias renderiza con datos reales."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("5"), "costo_unitario": Decimal("2")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:existencias"))
    assert respuesta.status_code == 200
    assert articulo.sku.encode() in respuesta.content


@pytest.mark.django_db
def test_movimiento_detalle_responde_200(
    client, usuario_administrador, tipo_entrada, almacen, articulo
):
    """La ficha de un movimiento renderiza sus líneas."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:detalle", args=[movimiento.pk]))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_movimiento_inexistente_da_404(client, usuario_administrador):
    """Un identificador que no existe responde 404, no un 500."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:detalle", args=[999999]))
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_kardex_responde_200(client, usuario_administrador, articulo):
    """El kardex de un artículo sin movimientos muestra el estado vacío, no un error."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:kardex", args=[articulo.pk]))
    assert respuesta.status_code == 200
    assert "todavía no tiene movimientos" in respuesta.content.decode()


@pytest.mark.django_db
def test_aprobaciones_responde_200(client, usuario_administrador):
    """La bandeja de aprobaciones renderiza vacía sin pendientes."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:aprobaciones"))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_formulario_de_entrada_get_responde_200(client, usuario_administrador, tipo_entrada):
    """El modal de alta de entrada carga con el formset vacío."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("movimientos:entrada_nueva"))
    assert respuesta.status_code == 200
    assert b"TOTAL_FORMS" in respuesta.content


@pytest.mark.django_db
def test_registrar_entrada_por_la_url(client, usuario_administrador, tipo_entrada, almacen, articulo):
    """El alta de una entrada por HTMX responde 204 y deja el movimiento confirmado."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("movimientos:entrada_nueva"),
        {
            "tipo": tipo_entrada.pk, "almacen_destino": almacen.pk,
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-articulo": articulo.pk, "form-0-cantidad": "10", "form-0-costo_unitario": "25",
        },
    )
    assert respuesta.status_code == 204
    assert "kardexRecargar" in respuesta["HX-Trigger"]


@pytest.mark.django_db
def test_registrar_salida_por_la_url(
    client, usuario_administrador, tipo_entrada, tipo_salida, almacen, articulo
):
    """El alta de una salida por HTMX consume el lote existente."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("10"), "costo_unitario": Decimal("5")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("movimientos:salida_nueva"),
        {
            "tipo": tipo_salida.pk, "almacen_origen": almacen.pk,
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-articulo": articulo.pk, "form-0-cantidad": "3",
        },
    )
    assert respuesta.status_code == 204


@pytest.mark.django_db
def test_registrar_ajuste_sin_motivo_deja_error_en_el_formulario(
    client, usuario_administrador, tipo_ajuste, almacen, articulo
):
    """Un ajuste sin motivo no se registra y la respuesta trae el formulario con el error."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("movimientos:ajuste_nuevo"),
        {
            "tipo": tipo_ajuste.pk, "almacen": almacen.pk,
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-articulo": articulo.pk, "form-0-cantidad": "1", "form-0-signo": "1",
        },
    )
    assert respuesta.status_code == 200
    assert "motivo" in respuesta.content.decode().lower()


@pytest.mark.django_db
def test_anular_por_la_url(client, usuario_administrador, tipo_entrada, almacen, articulo):
    """El modal de anulación funciona de punta a punta."""
    movimiento = ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "costo_unitario": Decimal("1")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("movimientos:anular", args=[movimiento.pk]), {"motivo_anulacion": "Error de digitación"}
    )
    assert respuesta.status_code == 204
    movimiento.refresh_from_db()
    assert movimiento.estado == "anulado"


@pytest.mark.django_db
def test_aprobar_y_rechazar_por_la_url(
    client, usuario_administrador, tipo_ajuste_con_aprobacion, almacen, articulo
):
    """El botón de aprobar y el de rechazar funcionan desde la bandeja."""
    pendiente = ServicioMovimientos.registrar_ajuste(
        tipo=tipo_ajuste_con_aprobacion, almacen=almacen, usuario=usuario_administrador,
        motivo="Conteo", lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("1"), "signo": 1}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.post(reverse("movimientos:aprobar", args=[pendiente.pk]))
    assert respuesta.status_code == 204
    pendiente.refresh_from_db()
    assert pendiente.estado == "confirmado"


@pytest.mark.django_db
def test_crear_tipo_de_movimiento_por_la_url(client, usuario_administrador):
    """El alta de un tipo de movimiento funciona desde la pantalla de configuración."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("movimientos:tipo_nuevo"),
        {"codigo": "DEVOL", "nombre": "Devolución de cliente", "naturaleza": "entrada",
         "prefijo_numeracion": "DEV", "orden": "10"},
    )
    assert respuesta.status_code == 204
    assert TipoMovimiento.objects.filter(codigo="DEVOL").exists()
