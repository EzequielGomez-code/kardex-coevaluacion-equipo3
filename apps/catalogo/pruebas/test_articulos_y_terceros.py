"""
Pruebas de artículos, proveedores, clientes y su relación de precios.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.catalogo.models import Articulo, ProveedorArticulo, UnidadMedida
from apps.catalogo.services import (
    ServicioArticulos,
    ServicioCategorias,
    ServicioClientes,
    ServicioProveedores,
)
from apps.configuracion.models import Parametro, TipoDato


@pytest.fixture
def categoria(db):
    """Una categoría de prueba."""
    return ServicioCategorias.crear("CEM", "Cemento", "", None)


@pytest.fixture
def unidad(db) -> UnidadMedida:
    """Una unidad de medida de prueba."""
    return UnidadMedida.objects.create(codigo="ud", nombre="Unidad")


@pytest.mark.django_db
def test_generar_sku_usa_el_formato_configurado(categoria):
    """El SKU sale del parámetro ``formato_sku``, no de un formato fijo en el código."""
    Parametro.objects.create(
        clave="formato_sku", valor="{categoria}-{secuencia:05d}", tipo=TipoDato.TEXTO,
        etiqueta="Formato del SKU", grupo="Catálogo",
    )
    sku = ServicioArticulos.generar_sku(categoria)
    assert sku == "CEM-00001"


@pytest.mark.django_db
def test_generar_sku_incrementa_en_cada_llamada(categoria):
    """Dos artículos seguidos de la misma categoría reciben SKU distintos."""
    Parametro.objects.create(
        clave="formato_sku", valor="{categoria}-{secuencia:05d}", tipo=TipoDato.TEXTO,
        etiqueta="Formato del SKU", grupo="Catálogo",
    )
    primero = ServicioArticulos.generar_sku(categoria)
    segundo = ServicioArticulos.generar_sku(categoria)
    assert primero != segundo
    assert primero == "CEM-00001"
    assert segundo == "CEM-00002"


@pytest.mark.django_db
def test_generar_sku_sin_parametro_usa_el_formato_de_reserva(categoria):
    """Sin el parámetro sembrado, se usa un formato de reserva razonable."""
    sku = ServicioArticulos.generar_sku(categoria)
    assert sku.startswith("CEM-")


@pytest.mark.django_db
def test_crear_articulo_sin_sku_lo_genera_solo(categoria, unidad):
    """Si no se indica SKU al crear, el servicio lo genera."""
    articulo = ServicioArticulos.crear(nombre="Cemento gris", categoria=categoria, unidad=unidad)
    assert articulo.sku


@pytest.mark.django_db
def test_crear_articulo_con_sku_duplicado_falla(categoria, unidad):
    """No se permiten dos artículos con el mismo SKU."""
    ServicioArticulos.crear(sku="CEM-001", nombre="Uno", categoria=categoria, unidad=unidad)
    with pytest.raises(ValidationError, match="SKU"):
        ServicioArticulos.crear(sku="CEM-001", nombre="Dos", categoria=categoria, unidad=unidad)


@pytest.mark.django_db
def test_crear_articulo_con_codigo_de_barras_duplicado_falla(categoria, unidad):
    """No se permiten dos artículos con el mismo código de barras."""
    ServicioArticulos.crear(
        sku="A", nombre="Uno", categoria=categoria, unidad=unidad, codigo_barras="123"
    )
    with pytest.raises(ValidationError, match="código de barras"):
        ServicioArticulos.crear(
            sku="B", nombre="Dos", categoria=categoria, unidad=unidad, codigo_barras="123"
        )


@pytest.mark.django_db
def test_dos_articulos_sin_codigo_de_barras_no_chocan(categoria, unidad):
    """Un código de barras vacío no cuenta como duplicado entre sí."""
    ServicioArticulos.crear(sku="A", nombre="Uno", categoria=categoria, unidad=unidad)
    ServicioArticulos.crear(sku="B", nombre="Dos", categoria=categoria, unidad=unidad)  # no falla


@pytest.mark.django_db
def test_dar_de_baja_sin_movimientos_borra_de_verdad(categoria, unidad):
    """Un artículo sin historial se elimina físicamente."""
    articulo = ServicioArticulos.crear(nombre="Cemento", categoria=categoria, unidad=unidad)
    ServicioArticulos.dar_de_baja(articulo)
    assert not Articulo.objects.filter(pk=articulo.pk).exists()


@pytest.mark.django_db
def test_crear_proveedor_valida_el_rnc(db):
    """Un proveedor con un RNC de dígito de control incorrecto no se puede crear."""
    with pytest.raises(ValidationError):
        ServicioProveedores.crear(codigo="PROV-1", razon_social="Ferretería X",
                                  tipo_documento="rnc", rnc="131389644")  # dígito malo


@pytest.mark.django_db
def test_crear_proveedor_con_rnc_valido(db):
    """Un RNC con dígito de control correcto sí se acepta."""
    proveedor = ServicioProveedores.crear(
        codigo="PROV-1", razon_social="Ferretería X", tipo_documento="rnc", rnc="131389643"
    )
    assert proveedor.rnc == "131389643"


@pytest.mark.django_db
def test_dos_proveedores_no_comparten_rnc(db):
    """El mismo RNC no puede repetirse entre dos proveedores."""
    ServicioProveedores.crear(
        codigo="PROV-1", razon_social="Uno", tipo_documento="rnc", rnc="131389643"
    )
    with pytest.raises(ValidationError, match="RNC"):
        ServicioProveedores.crear(
            codigo="PROV-2", razon_social="Dos", tipo_documento="rnc", rnc="131389643"
        )


@pytest.mark.django_db
def test_cliente_y_proveedor_pueden_compartir_rnc(db):
    """Un mismo RNC sí puede aparecer en un proveedor y en un cliente: son tablas distintas."""
    ServicioProveedores.crear(
        codigo="PROV-1", razon_social="Uno", tipo_documento="rnc", rnc="131389643"
    )
    cliente = ServicioClientes.crear(
        codigo="CLI-1", razon_social="El mismo, como cliente", tipo_documento="rnc",
        rnc="131389643",
    )
    assert cliente.rnc == "131389643"


@pytest.mark.django_db
def test_fijar_precio_preferido_es_exclusivo(categoria, unidad):
    """Marcar un proveedor como preferido le quita la marca a los demás del mismo artículo."""
    articulo = ServicioArticulos.crear(nombre="Cemento", categoria=categoria, unidad=unidad)
    prov1 = ServicioProveedores.crear(codigo="P1", razon_social="Uno")
    prov2 = ServicioProveedores.crear(codigo="P2", razon_social="Dos")

    ServicioProveedores.fijar_precio(prov1, articulo, precio_compra="100", es_preferido=True)
    ServicioProveedores.fijar_precio(prov2, articulo, precio_compra="95", es_preferido=True)

    relacion1 = ProveedorArticulo.objects.get(proveedor=prov1, articulo=articulo)
    relacion2 = ProveedorArticulo.objects.get(proveedor=prov2, articulo=articulo)
    assert relacion1.es_preferido is False
    assert relacion2.es_preferido is True


@pytest.mark.django_db
def test_fijar_precio_dos_veces_actualiza_en_vez_de_duplicar(categoria, unidad):
    """Llamar dos veces con el mismo proveedor y artículo actualiza la fila, no crea otra."""
    articulo = ServicioArticulos.crear(nombre="Cemento", categoria=categoria, unidad=unidad)
    proveedor = ServicioProveedores.crear(codigo="P1", razon_social="Uno")

    ServicioProveedores.fijar_precio(proveedor, articulo, precio_compra="100")
    ServicioProveedores.fijar_precio(proveedor, articulo, precio_compra="110")

    assert ProveedorArticulo.objects.filter(proveedor=proveedor, articulo=articulo).count() == 1
    relacion = ProveedorArticulo.objects.get(proveedor=proveedor, articulo=articulo)
    assert relacion.precio_compra == 110
