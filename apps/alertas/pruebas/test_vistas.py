"""Pruebas de las vistas de Alertas: permisos y circuito básico por HTTP."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.alertas.models import Alerta, EstadoAlerta, ReglaAlerta, TipoRegla
from apps.movimientos.services import ServicioMovimientos


@pytest.fixture
def regla_stock_bajo(db) -> ReglaAlerta:
    """Regla de existencia bajo mínimo."""
    return ReglaAlerta.objects.create(nombre="Existencia baja", tipo=TipoRegla.STOCK_BAJO)


@pytest.mark.django_db
@pytest.mark.parametrize("nombre_ruta", ["alertas:indice", "alertas:reglas"])
def test_las_pantallas_exigen_permiso(client, usuario_sin_permisos, nombre_ruta):
    """Ninguna pantalla del módulo se abre sin su permiso (Seguridad #4)."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse(nombre_ruta)).status_code == 403


@pytest.mark.django_db
def test_indice_responde_200_con_alertas(
    client, usuario_administrador, regla_stock_bajo, tipo_entrada, almacen, articulo
):
    """La bandeja de alertas renderiza una alerta recién generada."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("alertas:indice"))
    assert respuesta.status_code == 200
    assert articulo.sku.encode() in respuesta.content


@pytest.mark.django_db
def test_crear_regla_por_la_url(client, usuario_administrador):
    """El alta de una regla de alerta funciona de punta a punta."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("alertas:regla_nueva"),
        {"nombre": "Sin movimiento", "tipo": "sin_movimiento", "dias_umbral": "90", "activa": "on"},
    )
    assert respuesta.status_code == 204
    assert ReglaAlerta.objects.filter(nombre="Sin movimiento").exists()


@pytest.mark.django_db
def test_crear_regla_sin_dias_falla_para_tipos_que_lo_exigen(client, usuario_administrador):
    """Una regla de vencimiento sin días de margen no se guarda."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("alertas:regla_nueva"),
        {"nombre": "Por vencer", "tipo": "vencimiento_proximo", "activa": "on"},
    )
    assert respuesta.status_code == 200
    assert "días de margen" in respuesta.content.decode()


@pytest.mark.django_db
def test_cambiar_estado_de_alerta_por_la_url(
    client, usuario_administrador, regla_stock_bajo, tipo_entrada, almacen, articulo
):
    """El botón «Actualizar» cambia el estado de una alerta abierta."""
    ServicioMovimientos.registrar_entrada(
        tipo=tipo_entrada, almacen_destino=almacen, usuario=usuario_administrador,
        lineas=[{"articulo_id": articulo.pk, "cantidad": Decimal("3"), "costo_unitario": Decimal("10")}],
    )
    alerta = Alerta.objects.get(regla=regla_stock_bajo)
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("alertas:alerta_estado", args=[alerta.pk]), {"estado": EstadoAlerta.IGNORADA}
    )
    assert respuesta.status_code == 204
    alerta.refresh_from_db()
    assert alerta.estado == EstadoAlerta.IGNORADA
    assert alerta.resuelta_por == usuario_administrador


@pytest.mark.django_db
def test_evaluar_ahora_exige_permiso_de_resolver(client, usuario_administrador):
    """El botón «Evaluar ahora» responde 204 para quien tiene el permiso."""
    client.force_login(usuario_administrador)
    respuesta = client.post(reverse("alertas:evaluar_ahora"))
    assert respuesta.status_code == 204
