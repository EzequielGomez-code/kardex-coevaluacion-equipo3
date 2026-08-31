"""
Pruebas del comando ``sembrar`` y de las utilidades transversales.

El comando tiene que ser idempotente (punto 4.3 del brief) y las utilidades de
subida de archivos tienen que rechazar lo que no corresponde (Seguridad #11).
"""

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.configuracion.models import DefinicionCampo, Parametro
from apps.nucleo.models import Almacen, Permiso, Rol, Usuario
from apps.nucleo.utilidades import (
    sanear_celda_hoja_de_calculo,
    sanear_nombre_archivo,
    validar_archivo_subido,
)


def _sembrar() -> str:
    """Ejecuta el comando y devuelve su salida."""
    salida = StringIO()
    call_command("sembrar", "--contrasena", "ClaveDeSiembra2026", stdout=salida)
    return salida.getvalue()


@pytest.mark.django_db
def test_sembrar_carga_todo_lo_minimo(db):
    """La primera siembra deja el sistema utilizable."""
    _sembrar()

    assert Permiso.objects.count() == 25
    assert Rol.objects.count() == 7
    assert Usuario.objects.filter(username="admin").exists()
    assert Almacen.objects.count() == 2
    assert Parametro.objects.count() >= 10
    assert DefinicionCampo.objects.count() == 3


@pytest.mark.django_db
def test_sembrar_dos_veces_no_duplica(db):
    """Punto 4.3: el comando es idempotente."""
    _sembrar()
    conteos = (
        Permiso.objects.count(),
        Rol.objects.count(),
        Usuario.objects.count(),
        Almacen.objects.count(),
        Parametro.objects.count(),
        DefinicionCampo.objects.count(),
    )

    _sembrar()

    assert conteos == (
        Permiso.objects.count(),
        Rol.objects.count(),
        Usuario.objects.count(),
        Almacen.objects.count(),
        Parametro.objects.count(),
        DefinicionCampo.objects.count(),
    )


@pytest.mark.django_db
def test_sembrar_no_pisa_un_parametro_ya_editado(db):
    """Si alguien cambió un parámetro, la segunda siembra lo respeta."""
    _sembrar()
    parametro = Parametro.objects.get(clave="dias_sin_movimiento")
    parametro.valor = "15"
    parametro.save()

    _sembrar()

    assert Parametro.objects.get(clave="dias_sin_movimiento").valor == "15"


@pytest.mark.django_db
def test_el_administrador_sembrado_tiene_todos_los_permisos(db):
    """El usuario inicial queda con el rol de Administrador de TI."""
    _sembrar()
    admin = Usuario.objects.get(username="admin")

    assert admin.rol.nombre == "Administrador de TI"
    assert admin.tiene_permiso("configuracion.gestionar") is True
    assert admin.password.startswith("argon2$")


@pytest.mark.django_db
def test_los_roles_del_sistema_no_se_pueden_eliminar(db):
    """Un rol del fixture está protegido contra el borrado."""
    from apps.nucleo.services import ServicioRoles  # noqa: PLC0415

    _sembrar()
    rol = Rol.objects.get(nombre="Auditor")
    with pytest.raises(ValidationError, match="del sistema"):
        ServicioRoles.eliminar(rol)


@pytest.mark.django_db
def test_un_rol_con_usuarios_no_se_puede_eliminar(db):
    """Antes de borrar un rol hay que reasignar a su gente."""
    from apps.nucleo.services import ServicioRoles  # noqa: PLC0415

    rol = Rol.objects.create(nombre="Temporal")
    Usuario.objects.create(username="alguien", rol=rol)

    with pytest.raises(ValidationError, match="usuarios asignados"):
        ServicioRoles.eliminar(rol)


# ---------------------------------------------------------------------------
# Activar/desactivar y eliminar usuarios y almacenes
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_no_puede_desactivarse_a_si_mismo(usuario_administrador):
    """El guardia contra la autodesactivación cubre también a ``cambiar_estado``."""
    from apps.nucleo.services import ServicioUsuarios  # noqa: PLC0415

    with pytest.raises(ValidationError, match="propia cuenta"):
        ServicioUsuarios.cambiar_estado(
            usuario_administrador, False, solicitante=usuario_administrador
        )


@pytest.mark.django_db
def test_no_puede_eliminarse_a_si_mismo(usuario_administrador):
    """Nadie puede borrar su propia cuenta desde la pantalla de usuarios."""
    from apps.nucleo.services import ServicioUsuarios  # noqa: PLC0415

    with pytest.raises(ValidationError, match="propia cuenta"):
        ServicioUsuarios.eliminar(usuario_administrador, solicitante=usuario_administrador)


@pytest.mark.django_db
def test_eliminar_usuario_con_movimientos_falla(usuario_administrador):
    """Un usuario que ya registró movimientos no se elimina: rompería el kardex."""
    from apps.movimientos.models import Movimiento, Naturaleza, TipoMovimiento  # noqa: PLC0415
    from apps.nucleo.services import ServicioUsuarios  # noqa: PLC0415

    tipo = TipoMovimiento.objects.create(
        codigo="AJU", nombre="Ajuste", naturaleza=Naturaleza.AJUSTE
    )
    Movimiento.objects.create(
        numero="AJU-000001", tipo=tipo, naturaleza=Naturaleza.AJUSTE,
        usuario=usuario_administrador,
    )
    with pytest.raises(ValidationError, match="movimientos"):
        ServicioUsuarios.eliminar(usuario_administrador)


@pytest.mark.django_db
def test_eliminar_usuario_sin_movimientos_funciona(usuario_administrador):
    """Un usuario sin historial se elimina de verdad."""
    from apps.nucleo.services import ServicioUsuarios  # noqa: PLC0415

    ServicioUsuarios.eliminar(usuario_administrador)
    assert not Usuario.objects.filter(pk=usuario_administrador.pk).exists()


@pytest.mark.django_db
def test_eliminar_almacen_con_movimientos_falla(almacen, usuario_administrador):
    """Un almacén con movimientos registrados no se elimina."""
    from apps.movimientos.models import Movimiento, Naturaleza, TipoMovimiento  # noqa: PLC0415
    from apps.nucleo.services import ServicioAlmacenes  # noqa: PLC0415

    tipo = TipoMovimiento.objects.create(
        codigo="ENT", nombre="Entrada", naturaleza=Naturaleza.ENTRADA
    )
    Movimiento.objects.create(
        numero="ENT-000001", tipo=tipo, naturaleza=Naturaleza.ENTRADA,
        almacen_destino=almacen, usuario=usuario_administrador,
    )
    with pytest.raises(ValidationError, match="movimientos"):
        ServicioAlmacenes.eliminar(almacen)


@pytest.mark.django_db
def test_eliminar_almacen_sin_movimientos_funciona(almacen):
    """Un almacén sin movimientos se elimina sin problema."""
    from apps.nucleo.services import ServicioAlmacenes  # noqa: PLC0415

    ServicioAlmacenes.eliminar(almacen)
    assert not Almacen.objects.filter(pk=almacen.pk).exists()


@pytest.mark.django_db
def test_reiniciar_demo_vacia_y_vuelve_a_sembrar(db):
    """
    Tras un reinicio, el catálogo de demostración queda funcionando otra vez.

    ``sembrar_demo`` arma categorías con hijas (Categoria.padre se protege a
    sí mismo), así que este caso también ejercita esa limpieza previa al
    borrado en bloque, no solo el circuito feliz.
    """
    from apps.catalogo.models import Articulo  # noqa: PLC0415

    call_command("sembrar_demo")
    total_primera_vez = Articulo.objects.count()
    assert total_primera_vez > 0

    call_command("reiniciar_demo")

    assert Articulo.objects.count() == total_primera_vez


# ---------------------------------------------------------------------------
# Seguridad #11 — subida de archivos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Windows\\system32\\cmd.exe", "cmd.exe"),
        ("reporte final.pdf", "reporte_final.pdf"),
        ("...oculto.txt", "oculto.txt"),
        ("", "archivo"),
    ],
)
def test_el_nombre_de_archivo_se_sanea(entrada, esperado):
    """Se quitan rutas, espacios y puntos iniciales."""
    assert sanear_nombre_archivo(entrada) == esperado


# ---------------------------------------------------------------------------
# Inyección de fórmulas en reportes Excel/CSV
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ('=HYPERLINK("http://evil","x")', "'=HYPERLINK(\"http://evil\",\"x\")"),
        ("+cmd|'/c calc'!A1", "'+cmd|'/c calc'!A1"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("Martillo de uña 16oz", "Martillo de uña 16oz"),
    ],
)
def test_una_celda_que_empieza_como_formula_se_neutraliza(entrada, esperado):
    """Un nombre de artículo que arranca como fórmula no debe ejecutarse al abrir el archivo."""
    assert sanear_celda_hoja_de_calculo(entrada) == esperado


class _ArchivoFalso:
    """Sustituto mínimo de un archivo subido."""

    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size


def test_una_extension_no_permitida_es_rechazada():
    """Solo pasan las extensiones de la lista blanca."""
    with pytest.raises(ValidationError, match="Extensión no permitida"):
        validar_archivo_subido(_ArchivoFalso("programa.exe", 1024))


def test_un_archivo_demasiado_grande_es_rechazado():
    """El tope de tamaño se comprueba en el servidor."""
    with pytest.raises(ValidationError, match="supera el máximo"):
        validar_archivo_subido(_ArchivoFalso("informe.pdf", 50 * 1024 * 1024))


def test_un_archivo_valido_pasa():
    """Un PDF pequeño no levanta ninguna excepción."""
    validar_archivo_subido(_ArchivoFalso("informe.pdf", 1024))
