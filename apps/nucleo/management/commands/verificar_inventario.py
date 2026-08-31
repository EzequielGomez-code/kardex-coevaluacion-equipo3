"""
Comando de gestión: comprueba que las tres capas del inventario cuadren.

``MovimientoLinea`` es el libro mayor, ``Lote.cantidad_disponible`` es el
saldo consumible y ``Existencia`` es el agregado — las tres se derivan una de
otra, así que si algo las desalinea (un error en un cálculo, una migración a
medias, una intervención manual en la base) este comando lo encuentra sin
tener que revisarlo a mano. Sirve tanto para revisar la siembra de
demostración como para vigilar producción de vez en cuando.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from apps.movimientos.models import Existencia, Lote, MovimientoLinea

TOLERANCIA = Decimal("0.01")


class Command(BaseCommand):
    """Recalcula existencias desde los lotes y las líneas, y reporta cualquier diferencia."""

    help = "Verifica que Existencia, Lote y MovimientoLinea estén cuadrados entre sí."

    def handle(self, *args, **opciones) -> None:
        errores = 0
        errores += self._verificar_existencias_contra_lotes()
        errores += self._verificar_existencias_contra_lineas()
        errores += self._verificar_lotes_dentro_de_rango()

        if errores:
            self.stdout.write(self.style.ERROR(f"\nSe encontraron {errores} inconsistencia(s)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nEl inventario está cuadrado: sin inconsistencias."))

    def _verificar_existencias_contra_lotes(self) -> int:
        """La cantidad y el valor de cada existencia deben ser la suma de sus lotes vivos."""
        errores = 0
        lotes_por_par = (
            Lote.objects.values("articulo_id", "almacen_id")
            .annotate(
                cantidad=Sum("cantidad_disponible"),
                valor=Sum(
                    ExpressionWrapper(
                        F("cantidad_disponible") * F("costo_unitario"),
                        output_field=DecimalField(max_digits=18, decimal_places=4),
                    )
                ),
            )
        )
        totales = {
            (fila["articulo_id"], fila["almacen_id"]): (fila["cantidad"], fila["valor"])
            for fila in lotes_por_par
        }

        for existencia in Existencia.objects.select_related("articulo", "almacen"):
            clave = (existencia.articulo_id, existencia.almacen_id)
            cantidad_lotes, valor_lotes = totales.get(clave, (Decimal("0"), Decimal("0")))
            cantidad_lotes = cantidad_lotes or Decimal("0")
            valor_lotes = valor_lotes or Decimal("0")
            if abs(cantidad_lotes - existencia.cantidad) > TOLERANCIA:
                errores += 1
                self.stdout.write(self.style.ERROR(
                    f"  cantidad: {existencia.articulo.sku} en {existencia.almacen.codigo} — "
                    f"existencia={existencia.cantidad}, lotes={cantidad_lotes}"
                ))
            if abs(valor_lotes - existencia.valor) > TOLERANCIA:
                errores += 1
                self.stdout.write(self.style.ERROR(
                    f"  valor: {existencia.articulo.sku} en {existencia.almacen.codigo} — "
                    f"existencia={existencia.valor}, lotes={valor_lotes}"
                ))
        return errores

    def _verificar_existencias_contra_lineas(self) -> int:
        """La cantidad de cada existencia debe coincidir con la suma con signo de sus líneas."""
        errores = 0
        # Se suma a mano, con signo, en Python: Sum() no puede multiplicar dos
        # campos entre sí de forma portable entre SQLite y PostgreSQL.
        totales: dict[tuple[int, int], Decimal] = {}
        for linea in MovimientoLinea.objects.values("articulo_id", "almacen_id", "signo", "cantidad"):
            clave = (linea["articulo_id"], linea["almacen_id"])
            totales[clave] = totales.get(clave, Decimal("0")) + linea["signo"] * linea["cantidad"]

        for existencia in Existencia.objects.select_related("articulo", "almacen"):
            clave = (existencia.articulo_id, existencia.almacen_id)
            esperado = totales.get(clave, Decimal("0"))
            if abs(esperado - existencia.cantidad) > TOLERANCIA:
                errores += 1
                self.stdout.write(self.style.ERROR(
                    f"  kardex: {existencia.articulo.sku} en {existencia.almacen.codigo} — "
                    f"existencia={existencia.cantidad}, suma de líneas={esperado}"
                ))
        return errores

    def _verificar_lotes_dentro_de_rango(self) -> int:
        """Ningún lote puede tener menos de cero ni más de lo que entró."""
        errores = 0
        negativos = Lote.objects.filter(cantidad_disponible__lt=0)
        excedidos = [lote for lote in Lote.objects.all() if lote.cantidad_disponible > lote.cantidad_inicial]
        for lote in negativos:
            errores += 1
            self.stdout.write(
                self.style.ERROR(f"  lote negativo: {lote.codigo} ({lote.cantidad_disponible})")
            )
        for lote in excedidos:
            errores += 1
            self.stdout.write(self.style.ERROR(
                f"  lote excedido: {lote.codigo} (disponible={lote.cantidad_disponible}, "
                f"inicial={lote.cantidad_inicial})"
            ))
        return errores
