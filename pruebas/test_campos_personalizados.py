"""
Pruebas de los campos personalizados.

Es la pieza que hace configurable a Kardex: el usuario define campos desde la
pantalla y estos aparecen en el formulario correspondiente, con su validación
del lado del servidor (Seguridad #9).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.configuracion.models import DefinicionCampo, TipoDato, ValorCampo
from apps.configuracion.services import (
    ServicioCamposPersonalizados,
    ServicioDefinicionesCampo,
)


@pytest.mark.django_db
def test_campos_de_devuelve_solo_los_activos(campos_de_almacen):
    """Un campo desactivado deja de aparecer en los formularios."""
    campos_de_almacen[0].activo = False
    campos_de_almacen[0].save()

    claves = [c.clave for c in ServicioCamposPersonalizados.campos_de("Almacen")]
    assert "metros_cuadrados" not in claves
    assert "tipo_local" in claves


@pytest.mark.django_db
def test_campos_de_respeta_el_orden(campos_de_almacen):
    """Los campos salen en el orden que fijó el usuario al arrastrarlos."""
    claves = [c.clave for c in ServicioCamposPersonalizados.campos_de("Almacen")]
    assert claves == ["metros_cuadrados", "tipo_local", "responsable_seguridad"]


@pytest.mark.django_db
def test_una_categoria_suma_sus_campos_a_los_generales(db):
    """Un campo de categoría se ve solo en esa categoría; los generales, siempre."""
    DefinicionCampo.objects.create(
        entidad="Articulo", clave="color", etiqueta="Color", tipo=TipoDato.TEXTO
    )
    DefinicionCampo.objects.create(
        entidad="Articulo", categoria="Pinturas", clave="litros",
        etiqueta="Litros", tipo=TipoDato.DECIMAL,
    )

    generales = [c.clave for c in ServicioCamposPersonalizados.campos_de("Articulo")]
    pinturas = [
        c.clave for c in ServicioCamposPersonalizados.campos_de("Articulo", "Pinturas")
    ]

    assert generales == ["color"]
    assert sorted(pinturas) == ["color", "litros"]


@pytest.mark.django_db
def test_un_campo_obligatorio_vacio_falla(campos_de_almacen):
    """Sin el campo requerido, la validación del servidor rechaza el guardado."""
    with pytest.raises(ValidationError) as error:
        ServicioCamposPersonalizados.validar("Almacen", {"metros_cuadrados": "10"})
    assert "responsable_seguridad" in error.value.message_dict


@pytest.mark.django_db
def test_un_numero_mal_escrito_falla(campos_de_almacen):
    """Un decimal con letras no pasa."""
    with pytest.raises(ValidationError) as error:
        ServicioCamposPersonalizados.validar(
            "Almacen",
            {"metros_cuadrados": "doscientos", "responsable_seguridad": "Ana"},
        )
    assert "metros_cuadrados" in error.value.message_dict


@pytest.mark.django_db
def test_una_opcion_fuera_de_la_lista_falla(campos_de_almacen):
    """Un valor que no está entre las opciones definidas se rechaza."""
    with pytest.raises(ValidationError) as error:
        ServicioCamposPersonalizados.validar(
            "Almacen",
            {"tipo_local": "Ocupado", "responsable_seguridad": "Ana"},
        )
    assert "tipo_local" in error.value.message_dict


@pytest.mark.django_db
def test_los_valores_validos_se_convierten_a_su_tipo(campos_de_almacen):
    """La validación devuelve los valores ya convertidos, no cadenas."""
    limpios = ServicioCamposPersonalizados.validar(
        "Almacen",
        {
            "metros_cuadrados": "320.50",
            "tipo_local": "Alquilado",
            "responsable_seguridad": "Ana Pérez",
        },
    )
    assert limpios["metros_cuadrados"] == Decimal("320.50")
    assert limpios["tipo_local"] == "Alquilado"


@pytest.mark.django_db
def test_guardar_y_leer_los_valores_de_un_objeto(almacen, campos_de_almacen):
    """El circuito completo: se guardan los valores y se recuperan igual."""
    ServicioCamposPersonalizados.guardar_valores(
        almacen,
        {
            "metros_cuadrados": "450",
            "tipo_local": "Propio",
            "responsable_seguridad": "Luis Mena",
        },
        entidad="Almacen",
    )
    guardados = ServicioCamposPersonalizados.valores_de(almacen, "Almacen")

    assert guardados["metros_cuadrados"] == Decimal("450")
    assert guardados["tipo_local"] == "Propio"
    assert guardados["responsable_seguridad"] == "Luis Mena"


@pytest.mark.django_db
def test_guardar_dos_veces_no_duplica_valores(almacen, campos_de_almacen):
    """Volver a guardar actualiza la fila, no crea otra."""
    datos = {"tipo_local": "Propio", "responsable_seguridad": "Luis"}
    ServicioCamposPersonalizados.guardar_valores(almacen, datos, entidad="Almacen")
    datos["tipo_local"] = "Alquilado"
    ServicioCamposPersonalizados.guardar_valores(almacen, datos, entidad="Almacen")

    assert ValorCampo.objects.filter(definicion__clave="tipo_local").count() == 1
    valores = ServicioCamposPersonalizados.valores_de(almacen, "Almacen")
    assert valores["tipo_local"] == "Alquilado"


@pytest.mark.django_db
def test_cada_tipo_va_a_su_columna(almacen, db):
    """Los valores se reparten en las columnas tipadas de ``ValorCampo``."""
    DefinicionCampo.objects.create(
        entidad="Almacen", clave="fecha_apertura", etiqueta="Fecha de apertura",
        tipo=TipoDato.FECHA,
    )
    DefinicionCampo.objects.create(
        entidad="Almacen", clave="tiene_seguro", etiqueta="Tiene seguro",
        tipo=TipoDato.BOOLEANO,
    )

    ServicioCamposPersonalizados.guardar_valores(
        almacen, {"fecha_apertura": "15/03/2024", "tiene_seguro": "on"}, entidad="Almacen"
    )

    fecha = ValorCampo.objects.get(definicion__clave="fecha_apertura")
    booleano = ValorCampo.objects.get(definicion__clave="tiene_seguro")

    assert fecha.valor_fecha == dt.date(2024, 3, 15)
    assert fecha.valor_numero is None
    assert booleano.valor_bool is True


@pytest.mark.django_db
def test_no_se_repite_la_clave_en_la_misma_entidad(campos_de_almacen):
    """Dos campos con la misma clave en la misma entidad no se permiten."""
    with pytest.raises(ValidationError) as error:
        ServicioDefinicionesCampo.crear(
            entidad="Almacen", clave="tipo_local", etiqueta="Otro tipo",
            tipo=TipoDato.TEXTO,
        )
    assert "clave" in error.value.message_dict


@pytest.mark.django_db
def test_reordenar_guarda_el_nuevo_orden(campos_de_almacen):
    """Arrastrar las filas reescribe el campo ``orden``."""
    invertido = [campo.pk for campo in reversed(campos_de_almacen)]
    ServicioDefinicionesCampo.reordenar(invertido)

    claves = [c.clave for c in ServicioCamposPersonalizados.campos_de("Almacen")]
    assert claves == ["responsable_seguridad", "tipo_local", "metros_cuadrados"]


@pytest.mark.django_db
def test_el_formulario_dinamico_arma_los_widgets(campos_de_almacen):
    """El formulario se construye a partir de las definiciones activas."""
    from apps.configuracion.forms import FormularioCamposDinamicos  # noqa: PLC0415

    formulario = FormularioCamposDinamicos(entidad="Almacen")
    assert list(formulario.fields) == [
        "metros_cuadrados", "tipo_local", "responsable_seguridad",
    ]
    assert formulario.fields["responsable_seguridad"].required is True
    assert formulario.fields["tipo_local"].choices[1] == ("Propio", "Propio")


@pytest.mark.django_db
def test_guardar_campos_personalizados_deja_rastro_en_la_auditoria(
    campos_de_almacen, almacen
):
    """
    Punto 9.7 del brief: toda acción deja registro en la auditoría.

    Guardar campos personalizados escribía filas de ``ValorCampo`` sin dejar
    rastro, así que un cambio en esos datos era invisible para el auditor.
    """
    from apps.nucleo.models import RegistroAuditoria  # noqa: PLC0415

    ServicioCamposPersonalizados.guardar_valores(
        almacen,
        {
            "metros_cuadrados": "120",
            "tipo_local": "Propio",
            "responsable_seguridad": "Ramón Tolentino",
        },
        entidad="Almacen",
    )

    registro = RegistroAuditoria.objects.filter(
        entidad="Almacen", entidad_id=str(almacen.pk),
        accion=RegistroAuditoria.Accion.EDITAR,
    ).latest("creado_en")
    assert registro.detalle["accion_dominio"] == "campos_personalizados"
    assert registro.detalle["campos"] == [
        "metros_cuadrados", "responsable_seguridad", "tipo_local",
    ]


@pytest.mark.django_db
def test_borrar_campos_personalizados_deja_rastro_en_la_auditoria(
    campos_de_almacen, almacen
):
    """Dar de baja un objeto con campos propios también queda registrado."""
    from apps.nucleo.models import RegistroAuditoria  # noqa: PLC0415

    ServicioCamposPersonalizados.guardar_valores(
        almacen,
        {"metros_cuadrados": "120", "responsable_seguridad": "Ramón Tolentino"},
        entidad="Almacen",
    )
    ServicioCamposPersonalizados.borrar_valores(almacen, entidad="Almacen")

    registro = RegistroAuditoria.objects.filter(
        entidad="Almacen", entidad_id=str(almacen.pk),
        accion=RegistroAuditoria.Accion.ELIMINAR,
    ).latest("creado_en")
    assert registro.detalle["accion_dominio"] == "campos_personalizados"
    assert registro.detalle["borrados"] >= 1


@pytest.mark.django_db
def test_guardar_sin_campos_definidos_no_ensucia_la_auditoria(almacen):
    """Sin campos personalizados que guardar, no se escribe un registro vacío."""
    from apps.nucleo.models import RegistroAuditoria  # noqa: PLC0415

    antes = RegistroAuditoria.objects.count()
    ServicioCamposPersonalizados.guardar_valores(almacen, {}, entidad="Almacen")
    assert RegistroAuditoria.objects.count() == antes
