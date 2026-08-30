"""
Pruebas de la auditoría inmutable.

Seguridad #8 del brief (OWASP A09): un registro escrito no se puede modificar
ni eliminar, ni desde el código, ni desde el panel de administración.
"""

import pytest
from django.core.exceptions import PermissionDenied

from apps.nucleo.admin import AdminRegistroAuditoria
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAlmacenes, ServicioAuditoria


@pytest.fixture
def registro(db) -> RegistroAuditoria:
    """Un registro de auditoría ya escrito."""
    return RegistroAuditoria.objects.create(
        entidad="Almacen",
        entidad_id="1",
        accion=RegistroAuditoria.Accion.CREAR,
        detalle={"codigo": "ALM-01"},
        ip="10.0.0.1",
    )


@pytest.mark.django_db
def test_no_se_puede_modificar_un_registro(registro):
    """``save()`` sobre un registro existente lanza excepción."""
    registro.detalle = {"codigo": "MANIPULADO"}
    with pytest.raises(PermissionDenied, match="no se pueden modificar"):
        registro.save()


@pytest.mark.django_db
def test_el_contenido_no_cambia_tras_el_intento(registro):
    """Tras el intento fallido, lo guardado en la base sigue intacto."""
    registro.detalle = {"codigo": "MANIPULADO"}
    with pytest.raises(PermissionDenied):
        registro.save()

    desde_la_base = RegistroAuditoria.objects.get(pk=registro.pk)
    assert desde_la_base.detalle == {"codigo": "ALM-01"}


@pytest.mark.django_db
def test_no_se_puede_eliminar_un_registro(registro):
    """``delete()`` lanza excepción y el registro sigue ahí."""
    with pytest.raises(PermissionDenied, match="no se pueden eliminar"):
        registro.delete()
    assert RegistroAuditoria.objects.filter(pk=registro.pk).exists()


@pytest.mark.django_db
def test_el_panel_de_administracion_no_permite_tocar_la_auditoria(registro):
    """El ``ModelAdmin`` niega alta, cambio y borrado."""
    admin = AdminRegistroAuditoria(RegistroAuditoria, None)
    assert admin.has_add_permission(None) is False
    assert admin.has_change_permission(None, registro) is False
    assert admin.has_delete_permission(None, registro) is False


@pytest.mark.django_db
def test_la_insercion_si_esta_permitida(db):
    """La auditoría se puede escribir; lo que no se puede es reescribir."""
    antes = RegistroAuditoria.objects.count()
    ServicioAuditoria.registrar(
        entidad="Prueba", accion=RegistroAuditoria.Accion.CREAR, entidad_id=7
    )
    assert RegistroAuditoria.objects.count() == antes + 1


@pytest.mark.django_db
def test_crear_un_almacen_deja_su_rastro(db):
    """Toda acción de negocio pasa por un servicio que audita."""
    almacen = ServicioAlmacenes.crear(
        codigo="ALM-77", nombre="Depósito de prueba", direccion="", encargado=None
    )
    registro = RegistroAuditoria.objects.filter(
        entidad="Almacen", entidad_id=str(almacen.pk)
    ).first()

    assert registro is not None
    assert registro.accion == RegistroAuditoria.Accion.CREAR
    assert registro.detalle["codigo"] == "ALM-77"


@pytest.mark.django_db
def test_editar_un_almacen_guarda_el_antes_y_el_despues(almacen):
    """El detalle de una edición registra el valor anterior y el nuevo."""
    ServicioAlmacenes.actualizar(
        almacen,
        codigo=almacen.codigo,
        nombre="Nombre corregido",
        direccion=almacen.direccion,
        encargado=None,
        activo=True,
    )
    registro = RegistroAuditoria.objects.filter(
        entidad="Almacen", accion=RegistroAuditoria.Accion.EDITAR
    ).first()

    assert registro.detalle["nombre"]["antes"] == "Almacén de prueba"
    assert registro.detalle["nombre"]["despues"] == "Nombre corregido"


@pytest.mark.django_db
def test_los_registros_se_ordenan_del_mas_reciente_al_mas_viejo(db):
    """El listado empieza por lo último que pasó."""
    for numero in range(3):
        ServicioAuditoria.registrar(
            entidad="Prueba", accion=RegistroAuditoria.Accion.CREAR, entidad_id=numero
        )
    identificadores = list(RegistroAuditoria.objects.values_list("entidad_id", flat=True))
    assert identificadores == ["2", "1", "0"]
