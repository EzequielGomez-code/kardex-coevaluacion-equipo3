"""
Pruebas de las vistas del catálogo: permisos, altas por HTMX y el circuito
completo de mover/reordenar categorías a través de la URL.
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria, UnidadMedida
from apps.catalogo.services import ServicioArticulos, ServicioCategorias, ServicioProveedores


@pytest.fixture
def categoria(db) -> Categoria:
    """Una categoría raíz de prueba."""
    return ServicioCategorias.crear("CEM", "Cemento", "", None)


@pytest.fixture
def unidad(db) -> UnidadMedida:
    """Una unidad de medida de prueba."""
    return UnidadMedida.objects.create(codigo="UD", nombre="Unidad")


@pytest.fixture
def articulo(categoria, unidad) -> Articulo:
    """Un artículo de prueba."""
    return ServicioArticulos.crear(nombre="Cemento gris", categoria=categoria, unidad=unidad)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nombre_ruta,args",
    [
        ("catalogo:articulos", []),
        ("catalogo:categorias", []),
        ("catalogo:marcas", []),
        ("catalogo:unidades", []),
        ("catalogo:proveedores", []),
        ("catalogo:clientes", []),
    ],
)
def test_las_pantallas_de_listado_exigen_permiso(
    client, usuario_sin_permisos, nombre_ruta, args
):
    """Ninguna pantalla del catálogo se abre sin su permiso (Seguridad #4)."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse(nombre_ruta, args=args)).status_code == 403


@pytest.mark.django_db
def test_el_operador_ve_articulos_pero_no_gestiona_proveedores(client, usuario_operador):
    """El operador tiene articulo.ver pero no proveedor.gestionar."""
    client.force_login(usuario_operador)
    assert client.get(reverse("catalogo:articulos")).status_code == 200
    assert client.get(reverse("catalogo:proveedor_nuevo")).status_code == 403


@pytest.mark.django_db
def test_crear_articulo_por_htmx(client, usuario_administrador, categoria, unidad):
    """El alta de un artículo por HTMX responde 204 y deja el registro creado."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("catalogo:articulo_nuevo"),
        {
            "nombre": "Cemento blanco", "categoria": categoria.pk, "unidad": unidad.pk,
            "tasa_itbis": "18", "es_inventariable": "on", "maneja_lotes": "on",
        },
    )
    assert respuesta.status_code == 204
    assert "kardexRecargar" in respuesta["HX-Trigger"]
    assert Articulo.objects.filter(nombre="Cemento blanco").exists()


@pytest.mark.django_db
def test_crear_articulo_genera_sku_automatico(client, usuario_administrador, categoria, unidad):
    """Sin SKU explícito, el artículo creado por la pantalla recibe uno generado."""
    client.force_login(usuario_administrador)
    client.post(
        reverse("catalogo:articulo_nuevo"),
        {"nombre": "Varilla 3/8", "categoria": categoria.pk, "unidad": unidad.pk,
         "tasa_itbis": "18"},
    )
    articulo_creado = Articulo.objects.get(nombre="Varilla 3/8")
    assert articulo_creado.sku.startswith(categoria.codigo)


@pytest.mark.django_db
def test_editar_articulo_sin_permiso_de_edicion_da_403(client, usuario_operador, articulo):
    """El operador tiene articulo.ver pero no articulo.editar: no puede abrir el formulario."""
    client.force_login(usuario_operador)
    respuesta = client.get(reverse("catalogo:articulo_editar", args=[articulo.pk]))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_articulo_inexistente_da_404_amable(client, usuario_administrador):
    """Un identificador que no existe no revienta: responde con la plantilla de 404."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("catalogo:articulo_detalle", args=[999999]))
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_region_tabla_y_region_arbol_no_heredan_su_hx_swap_a_los_botones(
    client, usuario_administrador, categoria
):
    """
    ``#region-tabla``/``#region-arbol`` fijan su propio hx-swap="outerHTML"
    para su recarga automática; sin ``hx-disinherit``, cualquier botón
    «Editar» de adentro lo heredaba y HTMX terminaba reemplazando el modal
    entero por nada (el fragmento del editar no trae ``#region-tabla``/
    ``#region-arbol`` que el hx-select heredado busca).
    """
    client.force_login(usuario_administrador)

    marcas = client.get(reverse("catalogo:marcas"))
    assert b'id="region-tabla"' in marcas.content
    assert b'hx-disinherit="*"' in marcas.content

    categorias = client.get(reverse("catalogo:categorias"))
    assert b'id="region-arbol"' in categorias.content
    assert b'hx-disinherit="*"' in categorias.content


@pytest.mark.django_db
def test_crear_categoria_raiz_por_htmx(client, usuario_administrador):
    """El alta de una categoría raíz por HTMX crea el registro con ruta correcta."""
    client.force_login(usuario_administrador)
    respuesta = client.post(
        reverse("catalogo:categoria_nueva"),
        {"codigo": "PIN", "nombre": "Pinturas", "descripcion": "", "icono": "catalogo", "activo": "on"},
    )
    assert respuesta.status_code == 204
    categoria_creada = Categoria.objects.get(codigo="PIN")
    assert categoria_creada.padre is None
    assert categoria_creada.nivel == 0


@pytest.mark.django_db
def test_crear_subcategoria_con_padre_en_la_url(client, usuario_administrador, categoria):
    """El padre llega por ``?padre=`` y la subcategoría queda bajo él."""
    client.force_login(usuario_administrador)
    destino = f"{reverse('catalogo:categoria_nueva')}?padre={categoria.pk}"
    respuesta = client.post(
        destino,
        {"codigo": "SACOS", "nombre": "En saco", "descripcion": "", "icono": "catalogo", "activo": "on"},
    )
    assert respuesta.status_code == 204
    hija = Categoria.objects.get(codigo="SACOS")
    assert hija.padre_id == categoria.pk


@pytest.mark.django_db
def test_reordenar_categorias_por_la_url(client, usuario_administrador, categoria):
    """El endpoint de reordenamiento acepta JSON y reescribe las rutas."""
    client.force_login(usuario_administrador)
    primera = ServicioCategorias.crear("A", "Primera", "", categoria)
    segunda = ServicioCategorias.crear("B", "Segunda", "", categoria)

    respuesta = client.post(
        reverse("catalogo:categorias_reordenar"),
        data=json.dumps({"padre_id": categoria.pk, "orden": [segunda.pk, primera.pk]}),
        content_type="application/json",
    )
    assert respuesta.status_code == 200
    primera.refresh_from_db()
    segunda.refresh_from_db()
    assert segunda.ruta < primera.ruta


@pytest.mark.django_db
def test_mover_categoria_por_la_url(client, usuario_administrador, categoria):
    """El endpoint de traslado mueve una categoría a otro padre."""
    client.force_login(usuario_administrador)
    destino_nuevo = ServicioCategorias.crear("MAT", "Materiales", "", None)
    hija = ServicioCategorias.crear("SACOS", "En saco", "", categoria)

    respuesta = client.post(
        reverse("catalogo:categorias_mover"),
        data=json.dumps({"categoria_id": hija.pk, "nuevo_padre_id": destino_nuevo.pk}),
        content_type="application/json",
    )
    assert respuesta.status_code == 200
    hija.refresh_from_db()
    assert hija.padre_id == destino_nuevo.pk


@pytest.mark.django_db
def test_mover_categoria_a_su_propia_rama_da_error_json(client, usuario_administrador, categoria):
    """El intento de crear un ciclo se rechaza con un JSON de error, no un 500."""
    client.force_login(usuario_administrador)
    hija = ServicioCategorias.crear("SACOS", "En saco", "", categoria)

    respuesta = client.post(
        reverse("catalogo:categorias_mover"),
        data=json.dumps({"categoria_id": categoria.pk, "nuevo_padre_id": hija.pk}),
        content_type="application/json",
    )
    assert respuesta.status_code == 400
    assert "error" in respuesta.json()


@pytest.mark.django_db
def test_precio_de_proveedor_por_la_url(client, usuario_administrador, articulo):
    """Fijar un precio de proveedor desde la pantalla del artículo funciona de punta a punta."""
    client.force_login(usuario_administrador)
    proveedor = ServicioProveedores.crear(codigo="P1", razon_social="Ferretería Uno")

    respuesta = client.post(
        reverse("catalogo:precio_nuevo", args=[articulo.pk]),
        {"proveedor": proveedor.pk, "precio_compra": "150", "es_preferido": "on"},
    )
    assert respuesta.status_code == 204
    assert articulo.proveedores.filter(proveedor=proveedor, precio_compra=150).exists()


@pytest.mark.django_db
def test_alternar_estado_de_proveedor(client, usuario_administrador):
    """El botón de activar/desactivar invierte el estado del proveedor."""
    client.force_login(usuario_administrador)
    proveedor = ServicioProveedores.crear(codigo="P1", razon_social="Ferretería Uno")
    assert proveedor.activo is True

    respuesta = client.post(reverse("catalogo:proveedor_alternar", args=[proveedor.pk]))
    assert respuesta.status_code == 204
    proveedor.refresh_from_db()
    assert proveedor.activo is False


@pytest.mark.django_db
def test_campos_dinamicos_de_categoria_via_htmx(client, usuario_administrador, categoria):
    """El endpoint que recarga los campos personalizados responde 200 y trae el formulario."""
    from apps.configuracion.models import DefinicionCampo, TipoDato  # noqa: PLC0415

    DefinicionCampo.objects.create(
        entidad="Articulo", categoria=categoria.codigo, clave="peso_kg", etiqueta="Peso (kg)",
        tipo=TipoDato.DECIMAL,
    )
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("catalogo:articulo_campos"), {"categoria": categoria.pk})
    assert respuesta.status_code == 200
    assert "peso_kg" in respuesta.content.decode()
