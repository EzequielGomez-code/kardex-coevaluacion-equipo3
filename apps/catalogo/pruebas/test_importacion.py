"""
Pruebas de la importación masiva de artículos: procesamiento puro,
persistencia del mapeo de columnas, y el circuito completo por HTTP.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.catalogo.importacion import leer_texto, procesar, reporte_de_errores_csv
from apps.catalogo.models import Articulo, UnidadMedida
from apps.catalogo.services import ServicioCategorias, ServicioImportacionArticulos

MAPEO = {
    "sku": "sku", "nombre": "nombre", "descripcion": "", "categoria_codigo": "categoria",
    "marca_nombre": "", "unidad_codigo": "unidad", "codigo_barras": "", "costo_referencia": "costo",
    "precio_venta": "precio", "tasa_itbis": "", "stock_minimo_defecto": "",
}


@pytest.fixture
def unidad(db) -> UnidadMedida:
    """Una unidad de medida de prueba."""
    return UnidadMedida.objects.create(codigo="UD", nombre="Unidad")


@pytest.fixture
def categoria(db):
    """Una categoría raíz de prueba."""
    return ServicioCategorias.crear("FER", "Ferretería", "", None)


def _archivo(contenido: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("articulos.csv", contenido.encode("utf-8-sig"), content_type="text/csv")


@pytest.mark.django_db
def test_procesar_fila_valida_queda_lista_para_crear(categoria, unidad):
    """Una fila con categoría y unidad existentes se marca como válida."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,Cemento gris,FER,UD,150,200\n"
    filas = procesar(texto, MAPEO)
    assert len(filas) == 1
    assert filas[0].es_valida
    assert filas[0].datos["categoria"] == categoria
    assert filas[0].datos["unidad"] == unidad


@pytest.mark.django_db
def test_procesar_fila_con_categoria_inexistente_queda_marcada(unidad):
    """Una categoría que no existe se reporta por su código, no revienta el proceso."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,Cemento gris,NOEXISTE,UD,150,200\n"
    filas = procesar(texto, MAPEO)
    assert not filas[0].es_valida
    assert "NOEXISTE" in filas[0].errores[0]


@pytest.mark.django_db
def test_procesar_fila_sin_nombre_queda_marcada(categoria, unidad):
    """Un nombre vacío es un error, no un artículo silencioso sin nombre."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,,FER,UD,150,200\n"
    filas = procesar(texto, MAPEO)
    assert not filas[0].es_valida
    assert any("nombre" in error.lower() for error in filas[0].errores)


@pytest.mark.django_db
def test_procesar_respeta_tasa_itbis_y_minimo_explicitos_en_cero(categoria, unidad):
    """Un 0 escrito a propósito (exento de ITBIS, sin mínimo) no debe caer al valor por defecto."""
    mapeo = dict(MAPEO, tasa_itbis="itbis", stock_minimo_defecto="minimo")
    texto = (
        "sku,nombre,categoria,unidad,costo,precio,itbis,minimo\n"
        ",Cemento gris,FER,UD,150,200,0,0\n"
    )
    filas = procesar(texto, mapeo)
    assert filas[0].es_valida
    assert filas[0].datos["tasa_itbis"] == 0
    assert filas[0].datos["stock_minimo_defecto"] == 0


def test_leer_texto_decodifica_utf8_con_bom():
    """Un archivo con BOM UTF-8 (Excel) se lee sin dejar el BOM pegado al primer encabezado."""
    archivo = io.BytesIO("nombre\nCemento\n".encode("utf-8-sig"))
    texto = leer_texto(archivo)
    assert texto.startswith("nombre")


def test_leer_texto_cae_a_cp1252_si_no_es_utf8():
    """Un archivo en ANSI (Excel dominicano) no revienta al decodificar."""
    archivo = io.BytesIO("nombre\nTornillo Ñ\n".encode("cp1252"))
    texto = leer_texto(archivo)
    assert "Tornillo" in texto


@pytest.mark.django_db
def test_reporte_de_errores_solo_incluye_filas_invalidas(categoria, unidad):
    """El CSV de errores no repite las filas que sí se pudieron crear."""
    texto = (
        "sku,nombre,categoria,unidad,costo,precio\n"
        ",Cemento gris,FER,UD,150,200\n"
        ",Sin categoría,NOEXISTE,UD,10,20\n"
    )
    filas = procesar(texto, MAPEO)
    reporte = reporte_de_errores_csv(filas)
    assert "Sin categoría" in reporte
    assert "Cemento gris" not in reporte


@pytest.mark.django_db
def test_confirmar_crea_solo_las_filas_validas(categoria, unidad, usuario_administrador):
    """Confirmar la importación crea los artículos válidos y guarda el mapeo."""
    texto = (
        "sku,nombre,categoria,unidad,costo,precio\n"
        ",Cemento gris,FER,UD,150,200\n"
        ",Sin categoría,NOEXISTE,UD,10,20\n"
    )
    creados, con_error, _filas = ServicioImportacionArticulos.confirmar(
        _archivo(texto), MAPEO, usuario_administrador
    )
    assert creados == 1
    assert con_error == 1
    assert Articulo.objects.filter(nombre="Cemento gris").exists()
    assert not Articulo.objects.filter(nombre="Sin categoría").exists()

    guardado = ServicioImportacionArticulos.mapeo_guardado(usuario_administrador)
    assert guardado["categoria_codigo"] == "categoria"


@pytest.mark.django_db
def test_importar_pantalla_exige_permiso(client, usuario_sin_permisos):
    """Sin «importacion.ejecutar», la pantalla responde 403."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse("catalogo:articulo_importar")).status_code == 403


@pytest.mark.django_db
def test_previsualizar_por_la_url(client, usuario_administrador, categoria, unidad):
    """La vista previa por HTMX muestra cuántas filas quedaron listas."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,Cemento gris,FER,UD,150,200\n"
    client.force_login(usuario_administrador)
    datos = {**MAPEO, "archivo": _archivo(texto)}
    respuesta = client.post(reverse("catalogo:articulo_importar_previsualizar"), datos)
    assert respuesta.status_code == 200
    assert "Cemento gris" in respuesta.content.decode()
    assert not Articulo.objects.filter(nombre="Cemento gris").exists()


@pytest.mark.django_db
def test_confirmar_por_la_url_crea_el_articulo(client, usuario_administrador, categoria, unidad):
    """Confirmar por HTTP crea el artículo y muestra la pantalla de resultado."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,Cemento gris,FER,UD,150,200\n"
    client.force_login(usuario_administrador)
    datos = {**MAPEO, "archivo": _archivo(texto)}
    respuesta = client.post(reverse("catalogo:articulo_importar_confirmar"), datos)
    assert respuesta.status_code == 200
    assert Articulo.objects.filter(nombre="Cemento gris").exists()


@pytest.mark.django_db
def test_descargar_errores_por_la_url(client, usuario_administrador, unidad):
    """El botón de descargar errores devuelve un CSV con la fila que falló."""
    texto = "sku,nombre,categoria,unidad,costo,precio\n,Sin categoría,NOEXISTE,UD,10,20\n"
    client.force_login(usuario_administrador)
    datos = {**MAPEO, "archivo": _archivo(texto)}
    respuesta = client.post(reverse("catalogo:articulo_importar_errores"), datos)
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"].startswith("text/csv")
    assert b"Sin categoria" in respuesta.content or "Sin categoría".encode() in respuesta.content
