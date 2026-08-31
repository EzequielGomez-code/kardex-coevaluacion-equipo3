"""
Comando ``reiniciar_demo``: borra el catálogo, los movimientos y las alertas,
y vuelve a sembrar los datos de demostración desde cero.

Pensado para dejar el sistema listo para una presentación en vivo: borra lo
que haya quedado de pruebas anteriores (artículos, proveedores, clientes,
movimientos) y corre ``sembrar_demo`` de nuevo. No toca usuarios, roles,
almacenes ni parámetros — eso se conserva tal cual.

Uso::

    python manage.py reiniciar_demo
"""

from __future__ import annotations

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.alertas.models import Alerta, ReglaAlerta
from apps.catalogo.models import (
    Articulo,
    Categoria,
    Cliente,
    Marca,
    Proveedor,
    ProveedorArticulo,
    UnidadMedida,
)
from apps.movimientos.models import (
    ConsumoLote,
    Existencia,
    Lote,
    Movimiento,
    MovimientoLinea,
    TipoMovimiento,
)


class Command(BaseCommand):
    """Vacía el catálogo y los movimientos, y vuelve a sembrar la demo."""

    help = "Borra el catálogo, los movimientos y las alertas, y vuelve a sembrar la demo."

    @transaction.atomic
    def handle(self, *args: Any, **opciones: Any) -> None:
        """Vacía las tablas de demostración y llama a ``sembrar_demo``."""
        self.stdout.write(self.style.MIGRATE_HEADING("Vaciando datos de demostración"))
        self._vaciar()
        self.stdout.write(self.style.SUCCESS("Vaciado. Sembrando de nuevo:\n"))
        call_command("sembrar_demo")

    def _vaciar(self) -> None:
        """
        Borra en el orden que exigen las protecciones de la base.

        Dos autoenlaces (``Movimiento.anula`` y ``Categoria.padre``) se
        limpian primero con ``update()``: son protegidos, y borrar la tabla
        entera de una vez chocaría contra esa protección si una fila del
        lote todavía apunta a otra del mismo lote.
        """
        Movimiento.objects.update(anula=None)
        Categoria.objects.update(padre=None)

        Alerta.objects.all().delete()
        ReglaAlerta.objects.all().delete()
        ConsumoLote.objects.all().delete()
        Lote.objects.all().delete()
        MovimientoLinea.objects.all().delete()
        Movimiento.objects.all().delete()
        Existencia.objects.all().delete()
        ProveedorArticulo.objects.all().delete()
        Articulo.objects.all().delete()
        Cliente.objects.all().delete()
        Proveedor.objects.all().delete()
        TipoMovimiento.objects.all().delete()
        Categoria.objects.all().delete()
        UnidadMedida.objects.all().delete()
        Marca.objects.all().delete()
