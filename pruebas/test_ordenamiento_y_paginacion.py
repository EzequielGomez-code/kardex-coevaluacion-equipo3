"""
Pruebas del ordenamiento de tablas y la paginación configurable.

BRIEF 02, punto 2.4: "Toda tabla ordena por las columnas que dice ordenar."
El ordenamiento se valida contra una lista blanca para que una URL
manipulada no pueda ordenar por una columna no expuesta (OWASP A01).
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.configuracion.models import Parametro, TipoDato
from apps.nucleo.models import Almacen
from apps.nucleo.utilidades import ordenar, paginar

fabrica = RequestFactory()


@pytest.fixture
def tres_almacenes(db) -> list[Almacen]:
    """Tres almacenes con códigos y nombres en orden distinto entre sí."""
    return [
        Almacen.objects.create(codigo="ALM-03", nombre="Zeta"),
        Almacen.objects.create(codigo="ALM-01", nombre="Beta"),
        Almacen.objects.create(codigo="ALM-02", nombre="Alfa"),
    ]


def test_sin_parametro_orden_no_toca_la_consulta(tres_almacenes):
    """Sin ``?orden=`` en la URL, la consulta vuelve tal cual llegó."""
    request = fabrica.get("/almacenes/")
    resultado = ordenar(Almacen.objects.all(), request, {"codigo": "codigo"})
    assert list(resultado) == list(Almacen.objects.all())


def test_orden_ascendente_por_clave_permitida(tres_almacenes):
    """``?orden=codigo`` ordena de menor a mayor por el campo real."""
    request = fabrica.get("/almacenes/?orden=codigo")
    resultado = ordenar(Almacen.objects.all(), request, {"codigo": "codigo"})
    assert list(resultado.values_list("codigo", flat=True)) == ["ALM-01", "ALM-02", "ALM-03"]


def test_orden_descendente_con_sufijo(tres_almacenes):
    """``?orden=codigo-desc`` invierte el orden."""
    request = fabrica.get("/almacenes/?orden=codigo-desc")
    resultado = ordenar(Almacen.objects.all(), request, {"codigo": "codigo"})
    assert list(resultado.values_list("codigo", flat=True)) == ["ALM-03", "ALM-02", "ALM-01"]


def test_orden_por_otra_columna_permitida(tres_almacenes):
    """La lista blanca puede tener varias claves; cada una ordena por su campo."""
    request = fabrica.get("/almacenes/?orden=nombre")
    resultado = ordenar(
        Almacen.objects.all(), request, {"codigo": "codigo", "nombre": "nombre"}
    )
    assert list(resultado.values_list("nombre", flat=True)) == ["Alfa", "Beta", "Zeta"]


def test_una_clave_no_expuesta_se_ignora(tres_almacenes):
    """
    Una columna que no está en la lista blanca no ordena nada.

    Es la defensa contra una URL manipulada a mano que intente ordenar por un
    campo que la pantalla nunca declaró como ordenable.
    """
    request = fabrica.get("/almacenes/?orden=password")
    resultado = ordenar(Almacen.objects.all(), request, {"codigo": "codigo"})
    assert list(resultado) == list(Almacen.objects.all())


def test_una_clave_vacia_no_ordena(tres_almacenes):
    """``?orden=`` vacío se comporta igual que si no viniera el parámetro."""
    request = fabrica.get("/almacenes/?orden=")
    resultado = ordenar(Almacen.objects.all(), request, {"codigo": "codigo"})
    assert list(resultado) == list(Almacen.objects.all())


@pytest.mark.django_db
def test_paginar_usa_el_parametro_del_sistema_por_omision():
    """Sin ``por_pagina`` explícito, se lee ``filas_por_pagina`` del sistema."""
    Parametro.objects.create(
        clave="filas_por_pagina", valor="2", tipo=TipoDato.NUMERO,
        etiqueta="Filas por página", grupo="Formato",
    )
    for numero in range(5):
        Almacen.objects.create(codigo=f"ALM-{numero}", nombre=f"Depósito {numero}")

    request = fabrica.get("/almacenes/")
    resultado = paginar(request, Almacen.objects.all())

    assert resultado["paginador"].per_page == 2
    assert resultado["total"] == 5


@pytest.mark.django_db
def test_paginar_cae_al_valor_por_omision_sin_parametro():
    """Si el parámetro no existe todavía, se usa el valor de reserva (25)."""
    Almacen.objects.create(codigo="ALM-01", nombre="Depósito único")
    request = fabrica.get("/almacenes/")
    resultado = paginar(request, Almacen.objects.all())
    assert resultado["paginador"].per_page == 25


@pytest.mark.django_db
def test_paginar_respeta_un_valor_explicito():
    """Un ``por_pagina`` explícito sigue ganando, como en la auditoría (40)."""
    Parametro.objects.create(
        clave="filas_por_pagina", valor="2", tipo=TipoDato.NUMERO,
        etiqueta="Filas por página", grupo="Formato",
    )
    request = fabrica.get("/almacenes/")
    resultado = paginar(request, Almacen.objects.all(), por_pagina=40)
    assert resultado["paginador"].per_page == 40
