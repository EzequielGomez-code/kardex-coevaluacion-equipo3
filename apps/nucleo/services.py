"""
Servicios del núcleo.

Aquí viven las reglas de negocio de roles, usuarios, almacenes y auditoría.
Las vistas llaman a estos servicios y estos llaman a los repositorios; ninguna
vista consulta el ORM directamente (regla de capas del punto 3 del brief).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.nucleo.middleware import ip_actual, usuario_actual
from apps.nucleo.models import Almacen, RegistroAuditoria, Rol, Usuario
from apps.nucleo.repositories import (
    RepositorioAlmacenes,
    RepositorioAuditoria,
    RepositorioRoles,
    RepositorioUsuarios,
)

registro = logging.getLogger("kardex.nucleo")


class ServicioAuditoria:
    """
    Escribe el rastro inmutable de acciones (Seguridad #8 del brief).

    Toma el usuario y la IP del contexto de la petición, de modo que quien
    llama no necesita cargar el ``request`` hasta la capa de negocio.
    """

    @staticmethod
    def registrar(
        entidad: str,
        accion: str,
        entidad_id: Any = "",
        detalle: dict | None = None,
        usuario: Usuario | None = None,
        ip: str | None = None,
    ) -> RegistroAuditoria:
        """Deja constancia de una acción sobre una entidad del sistema."""
        # Ojo con el 0: es falso en Python, así que no se puede usar «or» aquí
        # sin perder el identificador.
        return RepositorioAuditoria.registrar(
            usuario=usuario if usuario is not None else usuario_actual(),
            entidad=entidad,
            entidad_id="" if entidad_id is None else str(entidad_id),
            accion=accion,
            detalle=detalle or {},
            ip=ip if ip is not None else ip_actual(),
        )

    @staticmethod
    def listar(**filtros) -> Any:
        """Devuelve el rastro filtrado, para la pantalla de auditoría."""
        return RepositorioAuditoria.listar(**filtros)

    @staticmethod
    def entidades() -> list[str]:
        """Devuelve las entidades presentes en el rastro, para el filtro."""
        return RepositorioAuditoria.entidades_registradas()


def _diferencias(antes: dict, despues: dict) -> dict:
    """Devuelve solo los campos que cambiaron, con su valor anterior y nuevo."""
    cambios: dict[str, dict[str, Any]] = {}
    for clave, valor_nuevo in despues.items():
        valor_viejo = antes.get(clave)
        if valor_viejo != valor_nuevo:
            cambios[clave] = {"antes": valor_viejo, "despues": valor_nuevo}
    return cambios


class ServicioRoles:
    """Alta, edición y asignación de permisos a roles."""

    @staticmethod
    def listar(busqueda: str = "") -> Any:
        """Devuelve los roles con su cantidad de usuarios."""
        return RepositorioRoles.listar(busqueda=busqueda)

    @staticmethod
    def obtener(rol_id: int) -> Rol | None:
        """Devuelve un rol por su identificador."""
        return RepositorioRoles.obtener(rol_id)

    @staticmethod
    def claves_de(rol: Rol) -> set[str]:
        """Devuelve las claves de permiso del rol."""
        return RepositorioRoles.claves_de(rol)

    @staticmethod
    @transaction.atomic
    def crear(nombre: str, descripcion: str, claves_permiso: Iterable[str]) -> Rol:
        """
        Crea un rol y le asigna sus permisos.

        :raises ValidationError: si ya existe un rol con ese nombre.
        """
        nombre = nombre.strip()
        if RepositorioRoles.obtener_por_nombre(nombre):
            raise ValidationError({"nombre": "Ya existe un rol con ese nombre."})

        rol = RepositorioRoles.crear(nombre=nombre, descripcion=descripcion.strip())
        claves = list(claves_permiso)
        RepositorioRoles.reemplazar_permisos(rol, claves)
        ServicioAuditoria.registrar(
            entidad="Rol",
            entidad_id=rol.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"nombre": rol.nombre, "permisos": sorted(claves)},
        )
        return rol

    @staticmethod
    @transaction.atomic
    def actualizar(rol: Rol, nombre: str, descripcion: str,
                   claves_permiso: Iterable[str]) -> Rol:
        """Actualiza los datos y los permisos de un rol existente."""
        nombre = nombre.strip()
        existente = RepositorioRoles.obtener_por_nombre(nombre)
        if existente and existente.pk != rol.pk:
            raise ValidationError({"nombre": "Ya existe un rol con ese nombre."})

        antes = {
            "nombre": rol.nombre,
            "descripcion": rol.descripcion,
            "permisos": sorted(RepositorioRoles.claves_de(rol)),
        }
        rol.nombre = nombre
        rol.descripcion = descripcion.strip()
        rol.save(update_fields=["nombre", "descripcion", "actualizado_en"])

        claves = sorted(set(claves_permiso))
        RepositorioRoles.reemplazar_permisos(rol, claves)

        despues = {"nombre": rol.nombre, "descripcion": rol.descripcion, "permisos": claves}
        ServicioAuditoria.registrar(
            entidad="Rol",
            entidad_id=rol.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle=_diferencias(antes, despues),
        )
        return rol

    @staticmethod
    @transaction.atomic
    def eliminar(rol: Rol) -> None:
        """
        Elimina un rol.

        :raises ValidationError: si es un rol del sistema o si todavía tiene
            usuarios asignados.
        """
        if rol.es_sistema:
            raise ValidationError("Los roles del sistema no se pueden eliminar.")
        if RepositorioRoles.cuenta_de_usuarios(rol):
            raise ValidationError(
                "Este rol tiene usuarios asignados. Reasígnelos antes de eliminarlo."
            )
        identificador, nombre = rol.pk, rol.nombre
        rol.delete()
        ServicioAuditoria.registrar(
            entidad="Rol",
            entidad_id=identificador,
            accion=RegistroAuditoria.Accion.ELIMINAR,
            detalle={"nombre": nombre},
        )


class ServicioUsuarios:
    """Alta, edición y desactivación de usuarios."""

    @staticmethod
    def listar(busqueda: str = "", rol_id: int | None = None, estado: str = "") -> Any:
        """Devuelve los usuarios filtrados."""
        return RepositorioUsuarios.listar(busqueda=busqueda, rol_id=rol_id, estado=estado)

    @staticmethod
    def obtener(usuario_id: int) -> Usuario | None:
        """Devuelve un usuario por su identificador."""
        return RepositorioUsuarios.obtener(usuario_id)

    @staticmethod
    @transaction.atomic
    def crear(username: str, nombre_completo: str, email: str, telefono: str,
              rol: Rol | None, contrasena: str, activo: bool = True) -> Usuario:
        """
        Crea un usuario con la contraseña ya cifrada con Argon2 (Seguridad #1).

        :raises ValidationError: si el nombre de acceso ya existe.
        """
        username = username.strip().lower()
        if RepositorioUsuarios.existe_nombre(username):
            raise ValidationError({"username": "Ese nombre de acceso ya está en uso."})

        usuario = Usuario(
            username=username,
            nombre_completo=nombre_completo.strip(),
            email=email.strip(),
            telefono=telefono.strip(),
            rol=rol,
            activo=activo,
        )
        usuario.set_password(contrasena)
        usuario.save()

        ServicioAuditoria.registrar(
            entidad="Usuario",
            entidad_id=usuario.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"username": usuario.username, "rol": rol.nombre if rol else None},
        )
        return usuario

    @staticmethod
    @transaction.atomic
    def actualizar(usuario: Usuario, nombre_completo: str, email: str, telefono: str,
                   rol: Rol | None, activo: bool,
                   contrasena: str = "") -> Usuario:
        """Actualiza un usuario; la contraseña solo cambia si se envía una nueva."""
        antes = {
            "nombre_completo": usuario.nombre_completo,
            "email": usuario.email,
            "telefono": usuario.telefono,
            "rol": usuario.rol.nombre if usuario.rol else None,
            "activo": usuario.activo,
        }
        usuario.nombre_completo = nombre_completo.strip()
        usuario.email = email.strip()
        usuario.telefono = telefono.strip()
        usuario.rol = rol
        usuario.activo = activo
        if contrasena:
            usuario.set_password(contrasena)
        usuario.save()

        despues = {
            "nombre_completo": usuario.nombre_completo,
            "email": usuario.email,
            "telefono": usuario.telefono,
            "rol": rol.nombre if rol else None,
            "activo": usuario.activo,
        }
        cambios = _diferencias(antes, despues)
        if contrasena:
            cambios["contrasena"] = {"antes": "***", "despues": "***"}
        ServicioAuditoria.registrar(
            entidad="Usuario",
            entidad_id=usuario.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle=cambios,
        )
        return usuario

    @staticmethod
    @transaction.atomic
    def cambiar_estado(usuario: Usuario, activo: bool,
                       solicitante: Usuario | None = None) -> Usuario:
        """
        Activa o desactiva un usuario.

        :raises ValidationError: si alguien intenta desactivarse a sí mismo.
        """
        if solicitante is not None and solicitante.pk == usuario.pk and not activo:
            raise ValidationError("No puede desactivar su propia cuenta.")
        usuario.activo = activo
        usuario.save(update_fields=["activo", "is_active"])
        ServicioAuditoria.registrar(
            entidad="Usuario",
            entidad_id=usuario.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"activo": {"antes": not activo, "despues": activo}},
        )
        return usuario


class ServicioAlmacenes:
    """Alta y edición de almacenes."""

    @staticmethod
    def listar(busqueda: str = "", estado: str = "") -> Any:
        """Devuelve los almacenes filtrados."""
        return RepositorioAlmacenes.listar(busqueda=busqueda, estado=estado)

    @staticmethod
    def activos() -> Any:
        """Devuelve los almacenes en operación."""
        return RepositorioAlmacenes.activos()

    @staticmethod
    def obtener(almacen_id: int) -> Almacen | None:
        """Devuelve un almacén por su identificador."""
        return RepositorioAlmacenes.obtener(almacen_id)

    @staticmethod
    @transaction.atomic
    def crear(codigo: str, nombre: str, direccion: str,
              encargado: Usuario | None, activo: bool = True) -> Almacen:
        """
        Crea un almacén.

        :raises ValidationError: si el código ya está en uso.
        """
        codigo = codigo.strip().upper()
        if RepositorioAlmacenes.existe_codigo(codigo):
            raise ValidationError({"codigo": "Ya existe un almacén con ese código."})

        almacen = Almacen.objects.create(
            codigo=codigo,
            nombre=nombre.strip(),
            direccion=direccion.strip(),
            encargado=encargado,
            activo=activo,
        )
        ServicioAuditoria.registrar(
            entidad="Almacen",
            entidad_id=almacen.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"codigo": almacen.codigo, "nombre": almacen.nombre},
        )
        return almacen

    @staticmethod
    @transaction.atomic
    def actualizar(almacen: Almacen, codigo: str, nombre: str, direccion: str,
                   encargado: Usuario | None, activo: bool) -> Almacen:
        """Actualiza los datos de un almacén."""
        codigo = codigo.strip().upper()
        if RepositorioAlmacenes.existe_codigo(codigo, excluir_id=almacen.pk):
            raise ValidationError({"codigo": "Ya existe un almacén con ese código."})

        antes = {
            "codigo": almacen.codigo,
            "nombre": almacen.nombre,
            "direccion": almacen.direccion,
            "encargado": str(almacen.encargado) if almacen.encargado else None,
            "activo": almacen.activo,
        }
        almacen.codigo = codigo
        almacen.nombre = nombre.strip()
        almacen.direccion = direccion.strip()
        almacen.encargado = encargado
        almacen.activo = activo
        almacen.save()

        despues = {
            "codigo": almacen.codigo,
            "nombre": almacen.nombre,
            "direccion": almacen.direccion,
            "encargado": str(encargado) if encargado else None,
            "activo": almacen.activo,
        }
        ServicioAuditoria.registrar(
            entidad="Almacen",
            entidad_id=almacen.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle=_diferencias(antes, despues),
        )
        return almacen
