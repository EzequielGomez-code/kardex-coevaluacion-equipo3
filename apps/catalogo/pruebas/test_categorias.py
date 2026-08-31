"""
Pruebas del árbol de categorías: la pieza de mayor riesgo del catálogo.

Cubren la ruta materializada, el reordenamiento entre hermanas y el traslado
de una categoría (con todo su subárbol) a otro padre, incluida la defensa
contra ciclos.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.catalogo.models import Articulo, Categoria
from apps.catalogo.services import ServicioCategorias


@pytest.mark.django_db
def test_crear_categoria_raiz_arma_la_ruta():
    """Una categoría sin padre queda en nivel 0 con una ruta de un segmento."""
    cat = ServicioCategorias.crear("CEM", "Cemento y agregados", "", None)
    assert cat.nivel == 0
    assert cat.ruta == "0010"
    assert cat.padre is None


@pytest.mark.django_db
def test_crear_categoria_hija_hereda_el_prefijo_del_padre():
    """La ruta de una hija empieza con la ruta completa del padre."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    hija = ServicioCategorias.crear("SACOS", "Cemento en saco", "", padre)
    assert hija.nivel == 1
    assert hija.ruta == f"{padre.ruta}.0010"


@pytest.mark.django_db
def test_dos_categorias_seguidas_incrementan_el_orden():
    """La segunda categoría bajo el mismo padre recibe un orden mayor."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    hija1 = ServicioCategorias.crear("A", "Primera", "", padre)
    hija2 = ServicioCategorias.crear("B", "Segunda", "", padre)
    assert hija2.orden > hija1.orden
    assert hija1.ruta < hija2.ruta


@pytest.mark.django_db
def test_codigo_repetido_bajo_el_mismo_padre_falla(db):
    """Dos hermanas no pueden compartir código, pero dos primas sí."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    ServicioCategorias.crear("A", "Primera", "", padre)
    with pytest.raises(ValidationError, match="Ya existe"):
        ServicioCategorias.crear("A", "Otra con el mismo código", "", padre)


@pytest.mark.django_db
def test_codigo_repetido_en_otra_rama_no_falla():
    """El mismo código puede repetirse en dos ramas distintas del árbol."""
    padre1 = ServicioCategorias.crear("CEM", "Cemento", "", None)
    padre2 = ServicioCategorias.crear("PIN", "Pinturas", "", None)
    ServicioCategorias.crear("A", "Bajo cemento", "", padre1)
    hija2 = ServicioCategorias.crear("A", "Bajo pinturas", "", padre2)  # no debe fallar
    assert hija2.codigo == "A"


@pytest.mark.django_db
def test_profundidad_maxima_se_respeta():
    """No se puede crear una categoría más allá del nivel 5."""
    actual = None
    for numero in range(6):  # niveles 0..5
        actual = ServicioCategorias.crear(f"N{numero}", f"Nivel {numero}", "", actual)
    with pytest.raises(ValidationError, match="niveles"):
        ServicioCategorias.crear("N6", "Nivel 6", "", actual)


@pytest.mark.django_db
def test_arbol_completo_sale_ordenado_por_ruta():
    """``arbol()`` devuelve las categorías ya en el orden de pantalla, sin recorrerlo a mano."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    ServicioCategorias.crear("B", "Segunda", "", padre)
    ServicioCategorias.crear("A", "Primera", "", padre)  # creada después, pero con orden mayor
    codigos = [c.codigo for c in ServicioCategorias.arbol()]
    assert codigos == ["CEM", "B", "A"]  # B se creó primero: le tocó el orden menor


@pytest.mark.django_db
def test_reordenar_hermanas_reescribe_las_rutas():
    """Reordenar dos hermanas les cambia el orden Y la ruta, sin colisiones."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    primera = ServicioCategorias.crear("A", "Primera", "", padre)
    segunda = ServicioCategorias.crear("B", "Segunda", "", padre)
    assert primera.ruta < segunda.ruta

    ServicioCategorias.reordenar(padre.pk, [segunda.pk, primera.pk])

    primera.refresh_from_db()
    segunda.refresh_from_db()
    assert segunda.ruta < primera.ruta
    assert segunda.orden < primera.orden


@pytest.mark.django_db
def test_reordenar_arrastra_a_los_hijos():
    """Al reordenar una categoría, su propia ruta cambia y sus hijas la siguen."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    primera = ServicioCategorias.crear("A", "Primera", "", padre)
    segunda = ServicioCategorias.crear("B", "Segunda", "", padre)
    nieta = ServicioCategorias.crear("A1", "Hija de la primera", "", primera)

    ServicioCategorias.reordenar(padre.pk, [segunda.pk, primera.pk])

    primera.refresh_from_db()
    nieta.refresh_from_db()
    assert nieta.ruta.startswith(f"{primera.ruta}.")
    assert nieta.padre_id == primera.pk


@pytest.mark.django_db
def test_reordenar_con_un_id_ajeno_falla():
    """Una lista de reordenamiento que no coincide con las hijas reales se rechaza."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    otra_rama = ServicioCategorias.crear("PIN", "Pinturas", "", None)
    hija = ServicioCategorias.crear("A", "Primera", "", padre)
    ajena = ServicioCategorias.crear("X", "De otra rama", "", otra_rama)

    with pytest.raises(ValidationError, match="no coincide"):
        ServicioCategorias.reordenar(padre.pk, [hija.pk, ajena.pk])


@pytest.mark.django_db
def test_mover_categoria_a_otro_padre():
    """Mover una categoría le cambia el padre, el nivel y la ruta."""
    origen = ServicioCategorias.crear("CEM", "Cemento", "", None)
    destino = ServicioCategorias.crear("MAT", "Materiales", "", None)
    hija = ServicioCategorias.crear("SACOS", "En saco", "", origen)

    movida = ServicioCategorias.mover(hija, destino)

    assert movida.padre_id == destino.pk
    assert movida.nivel == 1
    assert movida.ruta.startswith(f"{destino.ruta}.")


@pytest.mark.django_db
def test_mover_arrastra_el_subarbol_completo():
    """Al mover una categoría, todos sus descendientes cambian de ruta con ella."""
    origen = ServicioCategorias.crear("CEM", "Cemento", "", None)
    destino = ServicioCategorias.crear("MAT", "Materiales", "", None)
    hija = ServicioCategorias.crear("SACOS", "En saco", "", origen)
    nieta = ServicioCategorias.crear("50KG", "Sacos de 50kg", "", hija)

    ServicioCategorias.mover(hija, destino)

    nieta.refresh_from_db()
    hija.refresh_from_db()
    assert nieta.ruta.startswith(f"{hija.ruta}.")
    assert nieta.ruta.startswith(f"{destino.ruta}.")


@pytest.mark.django_db
def test_mover_una_categoria_dentro_de_su_propia_rama_falla():
    """No se puede mover un nodo a ser hijo de uno de sus propios descendientes: sería un ciclo."""
    abuelo = ServicioCategorias.crear("CEM", "Cemento", "", None)
    padre = ServicioCategorias.crear("SACOS", "En saco", "", abuelo)

    with pytest.raises(ValidationError, match="propia rama"):
        ServicioCategorias.mover(abuelo, padre)


@pytest.mark.django_db
def test_mover_a_si_misma_falla():
    """Una categoría no puede ser su propio padre."""
    cat = ServicioCategorias.crear("CEM", "Cemento", "", None)
    with pytest.raises(ValidationError, match="propio padre"):
        ServicioCategorias.mover(cat, cat)


@pytest.mark.django_db
def test_eliminar_categoria_con_hijas_falla():
    """No se elimina una categoría que todavía tiene subcategorías."""
    padre = ServicioCategorias.crear("CEM", "Cemento", "", None)
    ServicioCategorias.crear("A", "Hija", "", padre)
    with pytest.raises(ValidationError, match="subcategorías"):
        ServicioCategorias.eliminar(padre)


@pytest.mark.django_db
def test_eliminar_categoria_con_articulos_falla(db):
    """No se elimina una categoría con artículos asignados."""
    from apps.catalogo.models import UnidadMedida  # noqa: PLC0415

    categoria = ServicioCategorias.crear("CEM", "Cemento", "", None)
    unidad = UnidadMedida.objects.create(codigo="UD", nombre="Unidad")
    Articulo.objects.create(sku="CEM-001", nombre="Cemento gris", categoria=categoria, unidad=unidad)

    with pytest.raises(ValidationError, match="artículos"):
        ServicioCategorias.eliminar(categoria)


@pytest.mark.django_db
def test_eliminar_categoria_vacia_funciona():
    """Una categoría hoja, sin hijas ni artículos, se elimina sin problema."""
    categoria = ServicioCategorias.crear("VACIA", "Sin usar", "", None)
    ServicioCategorias.eliminar(categoria)
    assert not Categoria.objects.filter(pk=categoria.pk).exists()
