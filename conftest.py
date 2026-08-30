"""
Accesorios (fixtures) compartidos por toda la suite de pruebas.

Se declaran en la raíz para que los vean tanto ``pruebas/`` como las carpetas
``apps/*/pruebas/`` de los tres módulos funcionales.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.configuracion.models import DefinicionCampo, Parametro, TipoDato
from apps.nucleo.models import Almacen, Rol, Usuario

CONTRASENA_DE_PRUEBA = "PruebaKardex2026"


@pytest.fixture
def catalogo_de_permisos(db):
    """Carga el fixture de permisos y roles del sistema."""
    call_command("loaddata", "permisos_roles", verbosity=0)
    return Rol.objects.all()


@pytest.fixture
def rol_administrador(catalogo_de_permisos) -> Rol:
    """Devuelve el rol «Administrador de TI», que tiene todos los permisos."""
    return Rol.objects.get(nombre="Administrador de TI")


@pytest.fixture
def rol_operador(catalogo_de_permisos) -> Rol:
    """Devuelve el rol «Operador de almacén», con permisos limitados."""
    return Rol.objects.get(nombre="Operador de almacén")


@pytest.fixture
def rol_vacio(catalogo_de_permisos) -> Rol:
    """Rol sin ningún permiso, para probar el control de acceso."""
    return Rol.objects.create(nombre="Sin permisos", descripcion="Rol de prueba")


@pytest.fixture
def usuario_administrador(rol_administrador) -> Usuario:
    """Usuario con el rol de administrador (sin ser superusuario)."""
    usuario = Usuario(
        username="admin_prueba",
        nombre_completo="Administradora de prueba",
        email="admin@prueba.do",
        rol=rol_administrador,
    )
    usuario.set_password(CONTRASENA_DE_PRUEBA)
    usuario.save()
    return usuario


@pytest.fixture
def usuario_operador(rol_operador) -> Usuario:
    """Usuario con permisos de operador de almacén."""
    usuario = Usuario(
        username="operador_prueba",
        nombre_completo="Operador de prueba",
        rol=rol_operador,
    )
    usuario.set_password(CONTRASENA_DE_PRUEBA)
    usuario.save()
    return usuario


@pytest.fixture
def usuario_sin_permisos(rol_vacio) -> Usuario:
    """Usuario autenticado pero sin ningún permiso asignado."""
    usuario = Usuario(
        username="sin_permisos",
        nombre_completo="Usuario sin permisos",
        rol=rol_vacio,
    )
    usuario.set_password(CONTRASENA_DE_PRUEBA)
    usuario.save()
    return usuario


@pytest.fixture
def almacen(db) -> Almacen:
    """Un almacén de prueba."""
    return Almacen.objects.create(codigo="ALM-99", nombre="Almacén de prueba")


@pytest.fixture
def parametros_basicos(db) -> None:
    """Crea unos pocos parámetros representativos de cada tipo."""
    Parametro.objects.create(
        clave="moneda", valor="RD$", tipo=TipoDato.TEXTO,
        etiqueta="Símbolo de moneda", grupo="Formato",
    )
    Parametro.objects.create(
        clave="dias_sin_movimiento", valor="90", tipo=TipoDato.NUMERO,
        etiqueta="Días sin movimiento", grupo="Alertas",
    )
    Parametro.objects.create(
        clave="permitir_stock_negativo", valor="false", tipo=TipoDato.BOOLEANO,
        etiqueta="Permitir existencias negativas", grupo="Inventario",
    )
    Parametro.objects.create(
        clave="metodo_valoracion", valor="PEPS", tipo=TipoDato.LISTA,
        etiqueta="Método de valoración", grupo="Inventario",
        opciones=["PEPS", "UEPS", "Promedio ponderado"],
    )
    Parametro.objects.create(
        clave="version_esquema", valor="1", tipo=TipoDato.NUMERO,
        etiqueta="Versión del esquema", grupo="Sistema", editable=False,
    )


@pytest.fixture
def campos_de_almacen(db) -> list[DefinicionCampo]:
    """Tres definiciones de campo personalizado sobre la entidad Almacen."""
    return [
        DefinicionCampo.objects.create(
            entidad="Almacen", clave="metros_cuadrados", etiqueta="Metros cuadrados",
            tipo=TipoDato.DECIMAL, orden=10,
        ),
        DefinicionCampo.objects.create(
            entidad="Almacen", clave="tipo_local", etiqueta="Tipo de local",
            tipo=TipoDato.LISTA, opciones=["Propio", "Alquilado"], orden=20,
        ),
        DefinicionCampo.objects.create(
            entidad="Almacen", clave="responsable_seguridad",
            etiqueta="Responsable de seguridad", tipo=TipoDato.TEXTO,
            requerido=True, orden=30,
        ),
    ]
