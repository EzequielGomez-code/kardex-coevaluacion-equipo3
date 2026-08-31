"""
Modelos del núcleo: roles, permisos, usuarios, almacenes y auditoría.

Estos modelos son la base sobre la que trabajan las tres apps funcionales
(catálogo, movimientos y alertas). Ninguna regla de negocio vive aquí: los
modelos solo describen la forma de los datos y las invariantes que la base
de datos puede garantizar por sí sola.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# Rol técnico para reiniciar y recargar los datos de demostración (fixture
# permisos_roles.json). No se ofrece en el selector de «Nuevo usuario» ni en
# el listado de roles: se asigna a mano, fuera de la interfaz.
NOMBRE_ROL_OCULTO = "Superadministrador"


class ModeloConMarcaDeTiempo(models.Model):
    """Mezcla que añade las fechas de creación y actualización."""

    creado_en = models.DateTimeField("creado en", default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        abstract = True


class Rol(ModeloConMarcaDeTiempo):
    """
    Conjunto de permisos que se asigna a un usuario.

    Los roles marcados con ``es_sistema`` vienen del fixture inicial y no se
    pueden borrar desde la interfaz, para que nadie deje el sistema sin
    administrador por accidente.
    """

    nombre = models.CharField("nombre", max_length=60, unique=True)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    es_sistema = models.BooleanField(
        "es del sistema",
        default=False,
        help_text="Los roles del sistema no se pueden eliminar.",
    )
    permisos = models.ManyToManyField(
        "nucleo.Permiso",
        through="nucleo.RolPermiso",
        related_name="roles",
        verbose_name="permisos",
        blank=True,
    )

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Permiso(models.Model):
    """
    Permiso atómico identificado por una clave de la forma ``modulo.accion``.

    Se usa la clave y no el identificador numérico en todo el código, para que
    los permisos sobrevivan a un borrado y recarga del fixture.
    """

    clave = models.CharField(
        "clave",
        max_length=60,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z_]+\.[a-z_]+$",
                "La clave debe tener la forma modulo.accion, en minúsculas.",
            )
        ],
    )
    descripcion = models.CharField("descripción", max_length=200)
    modulo = models.CharField("módulo", max_length=40, db_index=True)

    class Meta:
        verbose_name = "permiso"
        verbose_name_plural = "permisos"
        ordering = ["modulo", "clave"]

    def __str__(self) -> str:
        return self.clave


class RolPermiso(models.Model):
    """Tabla puente entre :class:`Rol` y :class:`Permiso`."""

    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, verbose_name="rol")
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, verbose_name="permiso")

    class Meta:
        verbose_name = "permiso de rol"
        verbose_name_plural = "permisos de rol"
        constraints = [
            models.UniqueConstraint(fields=["rol", "permiso"], name="rol_permiso_unico"),
        ]

    def __str__(self) -> str:
        return f"{self.rol} → {self.permiso}"


class Usuario(AbstractUser):
    """
    Usuario del sistema. Hereda de ``AbstractUser`` para conservar el módulo de
    autenticación de Django (contraseñas con Argon2, sesiones, ``last_login``).

    El campo de dominio es ``activo``; ``is_active`` se mantiene sincronizado en
    ``save()`` porque es el que consulta el motor de autenticación de Django.
    """

    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        related_name="usuarios",
        verbose_name="rol",
        null=True,
        blank=True,
    )
    nombre_completo = models.CharField("nombre completo", max_length=150, blank=True)
    telefono = models.CharField("teléfono", max_length=30, blank=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.nombre_completo or self.username

    def save(self, *args, **kwargs):
        """Guarda el usuario manteniendo ``is_active`` alineado con ``activo``."""
        self.is_active = self.activo
        if not self.nombre_completo:
            self.nombre_completo = self.get_full_name() or self.username
        super().save(*args, **kwargs)

    @property
    def iniciales(self) -> str:
        """Devuelve hasta dos iniciales para el avatar de la barra superior."""
        partes = (self.nombre_completo or self.username).split()
        return "".join(parte[0].upper() for parte in partes[:2]) or "?"

    def claves_de_permiso(self) -> set[str]:
        """
        Devuelve el conjunto de claves de permiso del usuario.

        El resultado se memoriza en la instancia: durante una petición HTTP la
        instancia es la misma, así que el menú y los decoradores no repiten la
        consulta.
        """
        if not hasattr(self, "_cache_permisos"):
            if self.is_superuser:
                claves = set(Permiso.objects.values_list("clave", flat=True))
            elif self.rol_id:
                claves = set(
                    Permiso.objects.filter(roles__id=self.rol_id).values_list("clave", flat=True)
                )
            else:
                claves = set()
            self._cache_permisos = claves  # pylint: disable=attribute-defined-outside-init
        return self._cache_permisos

    def tiene_permiso(self, clave: str) -> bool:
        """Indica si el usuario puede ejecutar la acción identificada por ``clave``."""
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        return clave in self.claves_de_permiso()


class Almacen(ModeloConMarcaDeTiempo):
    """Depósito físico donde se guardan existencias."""

    codigo = models.CharField(
        "código",
        max_length=12,
        unique=True,
        validators=[
            RegexValidator(r"^[A-Z0-9-]+$", "Use mayúsculas, números o guiones.")
        ],
    )
    nombre = models.CharField("nombre", max_length=120)
    direccion = models.CharField("dirección", max_length=250, blank=True)
    encargado = models.ForeignKey(
        "nucleo.Usuario",
        on_delete=models.SET_NULL,
        related_name="almacenes_a_cargo",
        verbose_name="encargado",
        null=True,
        blank=True,
    )
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "almacén"
        verbose_name_plural = "almacenes"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nombre}"


class RegistroAuditoria(models.Model):
    """
    Rastro inmutable de toda acción relevante del sistema.

    Seguridad #8 del brief (OWASP A09 — Fallas de registro y monitoreo): una
    vez escrito, un registro no se puede modificar ni eliminar. ``save()``
    rechaza las actualizaciones y ``delete()`` lanza excepción, de modo que ni
    el panel de administración ni un descuido en el código puedan alterarlo.
    """

    class Accion(models.TextChoices):
        """Verbos permitidos en la auditoría."""

        CREAR = "crear", "Creó"
        EDITAR = "editar", "Editó"
        ELIMINAR = "eliminar", "Eliminó"
        INICIAR_SESION = "iniciar_sesion", "Inició sesión"
        CERRAR_SESION = "cerrar_sesion", "Cerró sesión"
        ACCESO_DENEGADO = "acceso_denegado", "Intento sin permiso"
        EXPORTAR = "exportar", "Exportó"

    usuario = models.ForeignKey(
        "nucleo.Usuario",
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
        verbose_name="usuario",
        null=True,
        blank=True,
    )
    entidad = models.CharField("entidad", max_length=60, db_index=True)
    entidad_id = models.CharField("id de la entidad", max_length=40, blank=True)
    accion = models.CharField("acción", max_length=20, choices=Accion.choices, db_index=True)
    detalle = models.JSONField("detalle", default=dict, blank=True)
    ip = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    creado_en = models.DateTimeField("creado en", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["entidad", "entidad_id"], name="auditoria_entidad_idx"),
            models.Index(fields=["-creado_en"], name="auditoria_fecha_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.creado_en:%d/%m/%Y %H:%M} · {self.usuario} · {self.accion} {self.entidad}"

    def save(self, *args, **kwargs):
        """Permite la inserción y rechaza cualquier actualización posterior."""
        if self.pk is not None:
            raise PermissionDenied(
                "Los registros de auditoría son inmutables: no se pueden modificar."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impide el borrado de un registro de auditoría."""
        raise PermissionDenied(
            "Los registros de auditoría son inmutables: no se pueden eliminar."
        )
