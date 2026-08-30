"""
Pruebas de Catálogo — las escribe Arturo.

La base ya deja configurado pytest-django: basta con marcar la prueba con
``@pytest.mark.django_db`` cuando necesite base de datos.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_el_modulo_exige_permiso(client, usuario_sin_permisos):
    """Sin el permiso del módulo, la pantalla responde 403 (Seguridad #4)."""
    client.force_login(usuario_sin_permisos)
    respuesta = client.get(reverse("catalogo:indice"))
    assert respuesta.status_code == 403
