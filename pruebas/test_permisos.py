"""
Pruebas de verificación de permisos.

Seguridad #4 del brief (OWASP A01): el permiso se comprueba en el servidor.
Ocultar el botón no basta; una petición directa por URL tiene que devolver 403.
"""

import pytest
from django.urls import reverse

from apps.nucleo.models import RegistroAuditoria


@pytest.mark.django_db
def test_sin_permiso_la_url_directa_devuelve_403(client, usuario_sin_permisos):
    """Un usuario autenticado sin el permiso recibe 403, no la pantalla."""
    client.force_login(usuario_sin_permisos)
    respuesta = client.get(reverse("nucleo:usuarios"))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_con_permiso_la_pantalla_responde(client, usuario_administrador):
    """Con el permiso correspondiente, la misma URL responde 200."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("nucleo:usuarios"))
    assert respuesta.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nombre_ruta",
    [
        "nucleo:usuarios",
        "nucleo:roles",
        "nucleo:almacenes",
        "nucleo:auditoria",
        "configuracion:parametros",
        "configuracion:campos",
        "configuracion:etiquetas",
    ],
)
def test_todas_las_pantallas_administrativas_exigen_permiso(
    client, usuario_sin_permisos, nombre_ruta
):
    """Ninguna pantalla administrativa se abre sin su permiso."""
    client.force_login(usuario_sin_permisos)
    assert client.get(reverse(nombre_ruta)).status_code == 403


@pytest.mark.django_db
def test_el_operador_ve_lo_suyo_y_no_lo_ajeno(client, usuario_operador):
    """
    El operador de almacén puede ver movimientos, pero no gestionar usuarios.

    Es el caso del criterio 9.3 del brief.
    """
    client.force_login(usuario_operador)
    assert usuario_operador.tiene_permiso("movimiento.crear") is True
    assert usuario_operador.tiene_permiso("usuario.gestionar") is False
    assert client.get(reverse("nucleo:usuarios")).status_code == 403
    assert client.get(reverse("movimientos:indice")).status_code == 200


@pytest.mark.django_db
def test_el_intento_sin_permiso_queda_en_la_auditoria(client, usuario_sin_permisos):
    """Cada 403 deja rastro con la ruta y el permiso que faltaba."""
    client.force_login(usuario_sin_permisos)
    client.get(reverse("nucleo:usuarios"))

    registro = RegistroAuditoria.objects.filter(
        accion=RegistroAuditoria.Accion.ACCESO_DENEGADO
    ).first()
    assert registro is not None
    assert registro.usuario_id == usuario_sin_permisos.pk
    assert registro.detalle["permisos_exigidos"] == ["usuario.gestionar"]


@pytest.mark.django_db
def test_el_menu_lateral_solo_trae_lo_permitido(client, usuario_operador):
    """El menú se recorta al rol, pero eso es solo comodidad visual."""
    client.force_login(usuario_operador)
    respuesta = client.get(reverse("nucleo:panel"))

    titulos = {
        enlace["titulo"]
        for seccion in respuesta.context["secciones_menu"]
        for enlace in seccion["enlaces"]
    }
    assert "Movimientos" in titulos
    assert "Usuarios" not in titulos
    assert "Parámetros" not in titulos


@pytest.mark.django_db
def test_el_superusuario_tiene_todos_los_permisos(db, catalogo_de_permisos):
    """Un superusuario pasa cualquier comprobación de permiso."""
    from apps.nucleo.models import Usuario  # noqa: PLC0415

    superusuario = Usuario.objects.create_superuser(
        username="raiz", password="ClaveDeRaiz2026", email="raiz@prueba.do"
    )
    assert superusuario.tiene_permiso("configuracion.gestionar") is True
    assert superusuario.tiene_permiso("permiso.inexistente") is True


@pytest.mark.django_db
def test_un_usuario_sin_rol_no_tiene_permisos(db):
    """Sin rol asignado, el conjunto de permisos es vacío."""
    from apps.nucleo.models import Usuario  # noqa: PLC0415

    usuario = Usuario.objects.create(username="huerfano", activo=True)
    assert usuario.claves_de_permiso() == set()
    assert usuario.tiene_permiso("articulo.ver") is False


@pytest.mark.django_db
def test_las_vistas_que_cambian_datos_rechazan_el_metodo_get(client, usuario_administrador):
    """Eliminar un rol solo se acepta por POST, nunca por GET."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("nucleo:rol_eliminar", args=[1]))
    assert respuesta.status_code == 405
