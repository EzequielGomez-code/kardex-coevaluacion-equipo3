"""
Pruebas de autenticación.

Cubren el punto 6.1 del brief (Argon2), el registro del acceso en la auditoría
y el rechazo de credenciales inválidas o de cuentas desactivadas.
"""

import pytest
from django.urls import reverse

from apps.nucleo.models import RegistroAuditoria, Usuario
from conftest import CONTRASENA_DE_PRUEBA


@pytest.mark.django_db
def test_la_contrasena_se_guarda_con_argon2(usuario_administrador):
    """Seguridad #1: el hash almacenado debe ser Argon2, no PBKDF2."""
    assert usuario_administrador.password.startswith("argon2$")
    assert usuario_administrador.check_password(CONTRASENA_DE_PRUEBA)


@pytest.mark.django_db
def test_la_contrasena_nunca_se_guarda_en_claro(usuario_administrador):
    """La contraseña original no debe aparecer en el campo almacenado."""
    assert CONTRASENA_DE_PRUEBA not in usuario_administrador.password


@pytest.mark.django_db
def test_acceso_con_credenciales_correctas(client, usuario_administrador):
    """Con usuario y contraseña válidos se entra y se redirige al panel."""
    respuesta = client.post(
        reverse("nucleo:iniciar_sesion"),
        {"username": usuario_administrador.username, "password": CONTRASENA_DE_PRUEBA},
    )
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("nucleo:panel")
    assert client.session.get("_auth_user_id") == str(usuario_administrador.pk)


@pytest.mark.django_db
def test_acceso_con_contrasena_incorrecta(client, usuario_administrador):
    """Una contraseña equivocada no abre sesión y no revela cuál campo falló."""
    respuesta = client.post(
        reverse("nucleo:iniciar_sesion"),
        {"username": usuario_administrador.username, "password": "clave-equivocada"},
    )
    assert respuesta.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "incorrectos" in respuesta.content.decode().lower()


@pytest.mark.django_db
def test_usuario_desactivado_no_puede_entrar(client, usuario_administrador):
    """Un usuario con ``activo=False`` queda fuera del sistema."""
    usuario_administrador.activo = False
    usuario_administrador.save()

    respuesta = client.post(
        reverse("nucleo:iniciar_sesion"),
        {"username": usuario_administrador.username, "password": CONTRASENA_DE_PRUEBA},
    )
    assert respuesta.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_el_acceso_queda_registrado_en_la_auditoria(client, usuario_administrador):
    """Seguridad #8: cada inicio de sesión deja rastro con usuario e IP."""
    client.post(
        reverse("nucleo:iniciar_sesion"),
        {"username": usuario_administrador.username, "password": CONTRASENA_DE_PRUEBA},
    )
    registro = RegistroAuditoria.objects.filter(
        accion=RegistroAuditoria.Accion.INICIAR_SESION
    ).first()

    assert registro is not None
    assert registro.usuario_id == usuario_administrador.pk
    assert registro.ip is not None


@pytest.mark.django_db
def test_cerrar_sesion_deja_rastro_y_limpia_la_sesion(client, usuario_administrador):
    """Al salir se registra la acción y la sesión queda vacía."""
    client.force_login(usuario_administrador)
    respuesta = client.get(reverse("nucleo:cerrar_sesion"))

    assert respuesta.status_code == 302
    assert "_auth_user_id" not in client.session
    assert RegistroAuditoria.objects.filter(
        accion=RegistroAuditoria.Accion.CERRAR_SESION
    ).exists()


@pytest.mark.django_db
def test_una_pantalla_protegida_redirige_al_acceso(client):
    """Sin sesión iniciada, una pantalla interna manda al formulario de acceso."""
    respuesta = client.get(reverse("nucleo:almacenes"))
    assert respuesta.status_code == 302
    assert reverse("nucleo:iniciar_sesion") in respuesta.url


@pytest.mark.django_db
def test_el_campo_activo_sincroniza_is_active(db, rol_vacio):
    """``activo`` es el campo de dominio; ``is_active`` lo sigue automáticamente."""
    usuario = Usuario(username="sincronia", rol=rol_vacio, activo=False)
    usuario.set_password(CONTRASENA_DE_PRUEBA)
    usuario.save()
    assert usuario.is_active is False

    usuario.activo = True
    usuario.save()
    assert usuario.is_active is True


@pytest.mark.django_db
def test_no_se_acepta_redireccion_a_sitio_externo(client, usuario_administrador):
    """El parámetro «siguiente» solo admite rutas internas (OWASP A01)."""
    respuesta = client.post(
        f"{reverse('nucleo:iniciar_sesion')}?siguiente=https://sitio-externo.example",
        {"username": usuario_administrador.username, "password": CONTRASENA_DE_PRUEBA},
    )
    assert respuesta.url == reverse("nucleo:panel")
