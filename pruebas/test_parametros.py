"""
Pruebas de los parámetros del sistema.

Criterio 9.6 del brief: se edita un parámetro y el cambio se refleja sin
reiniciar el servidor.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.configuracion.models import Parametro
from apps.configuracion.services import ServicioParametros
from apps.nucleo.models import RegistroAuditoria


@pytest.mark.django_db
def test_los_valores_se_devuelven_con_su_tipo(parametros_basicos):
    """Cada parámetro se convierte al tipo que declara, no queda como texto."""
    assert ServicioParametros.obtener("moneda") == "RD$"
    assert ServicioParametros.obtener("dias_sin_movimiento") == 90
    assert ServicioParametros.obtener("permitir_stock_negativo") is False


@pytest.mark.django_db
def test_un_parametro_inexistente_devuelve_el_valor_por_omision(parametros_basicos):
    """Pedir una clave que no existe no rompe: devuelve lo que se indique."""
    assert ServicioParametros.obtener("no_existe", "respaldo") == "respaldo"


@pytest.mark.django_db
def test_guardar_cambia_el_valor_de_inmediato(parametros_basicos):
    """
    El cambio se ve en la siguiente lectura, sin reiniciar nada.

    No hay caché entre peticiones justamente para que esto se cumpla.
    """
    assert ServicioParametros.obtener("dias_sin_movimiento") == 90
    ServicioParametros.guardar_muchos({"dias_sin_movimiento": "45"})
    assert ServicioParametros.obtener("dias_sin_movimiento") == 45


@pytest.mark.django_db
def test_guardar_devuelve_cuantos_cambiaron(parametros_basicos):
    """Solo cuentan los que efectivamente cambiaron de valor."""
    cantidad = ServicioParametros.guardar_muchos(
        {"moneda": "RD$", "dias_sin_movimiento": "30"}
    )
    assert cantidad == 1


@pytest.mark.django_db
def test_el_cambio_queda_en_la_auditoria(parametros_basicos):
    """Se registra el antes y el después de cada parámetro tocado."""
    ServicioParametros.guardar_muchos({"dias_sin_movimiento": "60"})
    registro = RegistroAuditoria.objects.filter(entidad="Parametro").first()

    assert registro is not None
    assert registro.detalle["dias_sin_movimiento"] == {"antes": "90", "despues": "60"}


@pytest.mark.django_db
def test_un_entero_invalido_es_rechazado(parametros_basicos):
    """Escribir letras en un parámetro numérico no se guarda."""
    with pytest.raises(ValidationError):
        ServicioParametros.guardar_muchos({"dias_sin_movimiento": "muchos"})
    assert ServicioParametros.obtener("dias_sin_movimiento") == 90


@pytest.mark.django_db
def test_una_opcion_fuera_de_la_lista_es_rechazada(parametros_basicos):
    """Un parámetro de lista solo admite sus opciones declaradas."""
    with pytest.raises(ValidationError):
        ServicioParametros.guardar_muchos({"metodo_valoracion": "Al ojo"})
    assert ServicioParametros.obtener("metodo_valoracion") == "PEPS"


@pytest.mark.django_db
def test_un_parametro_no_editable_no_cambia(parametros_basicos):
    """Los parámetros marcados como no editables se ignoran al guardar."""
    ServicioParametros.guardar_muchos({"version_esquema": "99"})
    assert ServicioParametros.obtener("version_esquema") == 1


@pytest.mark.django_db
def test_el_booleano_acepta_las_formas_del_formulario(parametros_basicos):
    """Una casilla marcada llega como «on»; una sin marcar, vacía."""
    ServicioParametros.guardar_muchos({"permitir_stock_negativo": "on"})
    assert ServicioParametros.obtener("permitir_stock_negativo") is True

    ServicioParametros.guardar_muchos({"permitir_stock_negativo": ""})
    assert ServicioParametros.obtener("permitir_stock_negativo") is False


@pytest.mark.django_db
def test_el_decimal_conserva_precision(db):
    """Un parámetro decimal no pierde los centavos."""
    Parametro.objects.create(
        clave="itbis", valor="0.18", tipo="decimal", etiqueta="ITBIS", grupo="Impuestos"
    )
    assert ServicioParametros.obtener("itbis") == Decimal("0.18")


@pytest.mark.django_db
def test_la_pantalla_refleja_el_cambio(client, usuario_administrador, parametros_basicos):
    """Tras guardar, la pantalla vuelve a leer el valor nuevo de la base."""
    from django.urls import reverse  # noqa: PLC0415

    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("configuracion:parametros"),
        {
            "moneda": "US$",
            "dias_sin_movimiento": "90",
            "permitir_stock_negativo": "",
            "metodo_valoracion": "PEPS",
        },
    )
    assert respuesta.status_code == 204

    contexto = client.get(reverse("configuracion:parametros")).context
    assert contexto["parametros"]["moneda"] == "US$"
