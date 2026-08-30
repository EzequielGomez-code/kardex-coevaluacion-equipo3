"""
Comando ``sembrar``: deja el sistema listo para usarse.

Carga permisos y roles desde el fixture, crea el usuario administrador, dos
almacenes de ejemplo, los parámetros por omisión y tres definiciones de campo
de muestra.

Es idempotente: correrlo dos veces no duplica nada. Cada paso busca antes de
crear y solo informa lo que efectivamente agregó.

Uso::

    python manage.py sembrar
    python manage.py sembrar --contrasena "una-clave-larga"
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.configuracion.models import DefinicionCampo, Etiqueta, Parametro, TipoDato
from apps.nucleo.models import Almacen, Rol, Usuario

# --------------------------------------------------------------------------
# Datos por omisión
# --------------------------------------------------------------------------
PARAMETROS = [
    ("moneda", "RD$", TipoDato.TEXTO, "Símbolo de moneda", "Formato", 10,
     "Se antepone a todo importe: RD$ 1,250.00.", []),
    ("formato_sku", "{categoria}-{secuencia:05d}", TipoDato.TEXTO, "Formato del SKU",
     "Catálogo", 10,
     "Plantilla para generar códigos de artículo. Admite categoria y secuencia.", []),
    ("permitir_stock_negativo", "false", TipoDato.BOOLEANO, "Permitir existencias negativas",
     "Inventario", 10,
     "Si está apagado, una salida no puede dejar la existencia por debajo de cero.", []),
    ("metodo_valoracion", "PEPS", TipoDato.LISTA, "Método de valoración", "Inventario", 20,
     "Regla con la que se valoran las salidas del inventario.",
     ["PEPS", "UEPS", "Promedio ponderado"]),
    ("dias_sin_movimiento", "90", TipoDato.NUMERO, "Días sin movimiento", "Alertas", 10,
     "A partir de cuántos días un artículo se considera sin rotación.", []),
    ("zona_horaria", "America/Santo_Domingo", TipoDato.TEXTO, "Zona horaria", "Formato", 20,
     "Zona horaria con la que se muestran las fechas.", []),
    ("stock_minimo_por_defecto", "5", TipoDato.NUMERO, "Existencia mínima por omisión",
     "Alertas", 20, "Valor que se sugiere al crear un artículo nuevo.", []),
    ("dias_vencimiento_aviso", "30", TipoDato.NUMERO, "Aviso de vencimiento (días)",
     "Alertas", 30, "Con cuántos días de antelación se avisa de un lote por vencer.", []),
    ("requiere_aprobacion_salida", "false", TipoDato.BOOLEANO,
     "Las salidas requieren aprobación", "Movimientos", 10,
     "Si está encendido, una salida queda pendiente hasta que un gerente la apruebe.", []),
    ("filas_por_pagina", "25", TipoDato.NUMERO, "Filas por página", "Formato", 30,
     "Cantidad de registros que muestra cada listado.", []),
]

ALMACENES = [
    ("ALM-01", "Almacén principal", "Av. Duarte 145, Santo Domingo"),
    ("ALM-02", "Sucursal Los Alcarrizos", "Carretera Duarte km 18, Los Alcarrizos"),
]

CAMPOS_MUESTRA = [
    {
        "entidad": "Almacen",
        "clave": "metros_cuadrados",
        "etiqueta": "Metros cuadrados",
        "tipo": TipoDato.DECIMAL,
        "orden": 10,
        "ayuda": "Superficie útil del local, para calcular capacidad.",
        "opciones": [],
        "requerido": False,
    },
    {
        "entidad": "Almacen",
        "clave": "tipo_local",
        "etiqueta": "Tipo de local",
        "tipo": TipoDato.LISTA,
        "orden": 20,
        "ayuda": "Régimen bajo el que se ocupa el local.",
        "opciones": ["Propio", "Alquilado", "Cedido"],
        "requerido": False,
    },
    {
        "entidad": "Articulo",
        "clave": "peso_kg",
        "etiqueta": "Peso (kg)",
        "tipo": TipoDato.DECIMAL,
        "orden": 10,
        "ayuda": "Peso unitario. Lo usará el módulo de catálogo.",
        "opciones": [],
        "requerido": False,
    },
]

ETIQUETAS = [
    ("Frágil", "#A03A22"),
    ("Alta rotación", "#3B6E2A"),
    ("Bajo pedido", "#8A6410"),
]


def contrasena_aleatoria(largo: int = 16) -> str:
    """Genera una contraseña fuerte para el administrador inicial."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


class Command(BaseCommand):
    """Carga los datos mínimos para que Kardex funcione."""

    help = "Carga permisos, roles, administrador, almacenes, parámetros y campos de muestra."

    def add_arguments(self, parser) -> None:
        """Declara las opciones del comando."""
        parser.add_argument(
            "--usuario", default="admin", help="Nombre de acceso del administrador."
        )
        parser.add_argument(
            "--contrasena",
            default="",
            help="Contraseña del administrador. Si se omite se toma de "
                 "DJANGO_ADMIN_PASSWORD o se genera una al azar.",
        )
        parser.add_argument(
            "--correo", default="admin@ferreteriamyf.do", help="Correo del administrador."
        )

    @transaction.atomic
    def handle(self, *args: Any, **opciones: Any) -> None:
        """Ejecuta la siembra completa, paso por paso."""
        self.stdout.write(self.style.MIGRATE_HEADING("Sembrando datos iniciales de Kardex"))

        self._sembrar_permisos_y_roles()
        self._sembrar_administrador(opciones)
        self._sembrar_almacenes()
        self._sembrar_parametros()
        self._sembrar_campos()
        self._sembrar_etiquetas()

        self.stdout.write(self.style.SUCCESS("\nSiembra terminada."))

    # -- Pasos --------------------------------------------------------------
    def _sembrar_permisos_y_roles(self) -> None:
        """Carga el fixture de permisos, roles y sus asignaciones."""
        call_command("loaddata", "permisos_roles", verbosity=0)
        self.stdout.write(
            f"  permisos y roles ......... {Rol.objects.count()} roles cargados del fixture"
        )

    def _sembrar_administrador(self, opciones: dict) -> None:
        """Crea el usuario administrador si todavía no existe."""
        username = opciones["usuario"]
        if Usuario.objects.filter(username=username).exists():
            self.stdout.write(f"  administrador ............ «{username}» ya existía")
            return

        contrasena = opciones["contrasena"] or getattr(
            settings, "CONTRASENA_ADMIN_INICIAL", ""
        )
        fue_generada = not contrasena
        if fue_generada:
            contrasena = contrasena_aleatoria()

        rol_ti = Rol.objects.filter(nombre="Administrador de TI").first()

        usuario = Usuario(
            username=username,
            email=opciones["correo"],
            nombre_completo="Administrador de TI",
            rol=rol_ti,
            is_staff=True,
            is_superuser=True,
            activo=True,
        )
        usuario.set_password(contrasena)
        usuario.save()

        self.stdout.write(f"  administrador ............ «{username}» creado")
        if fue_generada:
            self.stdout.write(
                self.style.WARNING(f"      contraseña generada al azar: {contrasena}")
            )
            self.stdout.write("      anótela: no se vuelve a mostrar.")
        else:
            self.stdout.write("      contraseña tomada de DJANGO_ADMIN_PASSWORD")

    def _sembrar_almacenes(self) -> None:
        """Crea los dos almacenes de ejemplo."""
        creados = 0
        for codigo, nombre, direccion in ALMACENES:
            _, nuevo = Almacen.objects.get_or_create(
                codigo=codigo, defaults={"nombre": nombre, "direccion": direccion}
            )
            creados += int(nuevo)
        self.stdout.write(
            f"  almacenes ................ {creados} creados, "
            f"{Almacen.objects.count()} en total"
        )

    def _sembrar_parametros(self) -> None:
        """Crea los parámetros por omisión sin pisar los ya editados."""
        creados = 0
        for clave, valor, tipo, etiqueta, grupo, orden, ayuda, opciones in PARAMETROS:
            _, nuevo = Parametro.objects.get_or_create(
                clave=clave,
                defaults={
                    "valor": valor,
                    "tipo": tipo,
                    "etiqueta": etiqueta,
                    "grupo": grupo,
                    "orden": orden,
                    "ayuda": ayuda,
                    "opciones": opciones,
                    "editable": True,
                },
            )
            creados += int(nuevo)
        self.stdout.write(
            f"  parámetros ............... {creados} creados, "
            f"{Parametro.objects.count()} en total"
        )

    def _sembrar_campos(self) -> None:
        """Crea las tres definiciones de campo de muestra."""
        creados = 0
        for datos in CAMPOS_MUESTRA:
            _, nuevo = DefinicionCampo.objects.get_or_create(
                entidad=datos["entidad"],
                categoria="",
                clave=datos["clave"],
                defaults={
                    "etiqueta": datos["etiqueta"],
                    "tipo": datos["tipo"],
                    "orden": datos["orden"],
                    "ayuda": datos["ayuda"],
                    "opciones": datos["opciones"],
                    "requerido": datos["requerido"],
                    "activo": True,
                },
            )
            creados += int(nuevo)
        self.stdout.write(
            f"  campos personalizados .... {creados} creados, "
            f"{DefinicionCampo.objects.count()} en total"
        )

    def _sembrar_etiquetas(self) -> None:
        """Crea tres etiquetas de ejemplo."""
        creadas = 0
        for nombre, color in ETIQUETAS:
            _, nueva = Etiqueta.objects.get_or_create(
                nombre=nombre, defaults={"color": color}
            )
            creadas += int(nueva)
        self.stdout.write(
            f"  etiquetas ................ {creadas} creadas, "
            f"{Etiqueta.objects.count()} en total"
        )
