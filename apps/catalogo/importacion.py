"""
Importación masiva de artículos desde un archivo CSV.

Entre la vista previa, la confirmación y la descarga de errores no se guarda
el archivo en el servidor: el formulario reenvía el mismo
``<input type="file">`` y este módulo lo vuelve a leer cada vez. El sistema
de archivos de Render es efímero, así que un archivo intermedio solo
agregaría un punto de falla — el costo es leer el archivo hasta tres veces,
aceptable para los lotes de un par de miles de filas que puede subir a mano
una ferretería.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.catalogo.models import Categoria, Marca, UnidadMedida

# Columnas del sistema que la persona puede mapear a los encabezados de su
# archivo. El orden es el que se muestra en el formulario de mapeo.
COLUMNAS_SISTEMA = [
    ("sku", "SKU", False),
    ("nombre", "Nombre", True),
    ("descripcion", "Descripción", False),
    ("categoria_codigo", "Código de categoría", True),
    ("marca_nombre", "Marca", False),
    ("unidad_codigo", "Código de unidad", True),
    ("codigo_barras", "Código de barras", False),
    ("costo_referencia", "Costo de referencia", False),
    ("precio_venta", "Precio de venta", False),
    ("tasa_itbis", "Tasa de ITBIS", False),
    ("stock_minimo_defecto", "Existencia mínima", False),
]


def leer_texto(archivo) -> str:
    """Decodifica el archivo subido, con caída a cp1252 — Excel dominicano exporta en ANSI."""
    contenido = archivo.read()
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("cp1252")


@dataclass
class FilaImportada:
    """Una fila del archivo, ya con sus datos preparados y sus errores (si tiene)."""

    numero: int
    crudo: dict
    datos: dict
    errores: list[str] = field(default_factory=list)

    @property
    def es_valida(self) -> bool:
        """Indica si la fila pasó la validación y está lista para crear su artículo."""
        return not self.errores


def _decimal_o_none(valor: str) -> Decimal | None:
    if not valor or not valor.strip():
        return None
    try:
        return Decimal(valor.strip().replace(",", ""))
    except InvalidOperation:
        return None


def procesar(texto: str, mapeo: dict[str, str]) -> list[FilaImportada]:
    """
    Aplica ``mapeo`` (campo del sistema → encabezado del archivo) a cada fila
    y valida lo que se puede validar sin tocar la base todavía: nombre,
    categoría y unidad existentes.
    """
    lector = csv.DictReader(io.StringIO(texto))
    categorias = {categoria.codigo: categoria for categoria in Categoria.objects.all()}
    unidades = {unidad.codigo: unidad for unidad in UnidadMedida.objects.all()}
    marcas = {marca.nombre.lower(): marca for marca in Marca.objects.all()}

    filas = []
    for numero, fila_cruda in enumerate(lector, start=2):  # la fila 1 es el encabezado
        datos_texto = {
            campo: (fila_cruda.get(encabezado, "") or "").strip()
            for campo, encabezado in mapeo.items() if encabezado
        }
        errores = []

        if not datos_texto.get("nombre"):
            errores.append("Falta el nombre.")

        codigo_categoria = datos_texto.get("categoria_codigo", "")
        categoria = categorias.get(codigo_categoria)
        if not categoria:
            errores.append(f"No existe la categoría «{codigo_categoria}».")

        codigo_unidad = datos_texto.get("unidad_codigo", "")
        unidad = unidades.get(codigo_unidad)
        if not unidad:
            errores.append(f"No existe la unidad «{codigo_unidad}».")

        nombre_marca = datos_texto.get("marca_nombre", "")
        marca = marcas.get(nombre_marca.lower()) if nombre_marca else None
        if nombre_marca and not marca:
            errores.append(f"No existe la marca «{nombre_marca}».")

        preparados = {
            "sku": datos_texto.get("sku", ""),
            "nombre": datos_texto.get("nombre", ""),
            "descripcion": datos_texto.get("descripcion", ""),
            "categoria": categoria,
            "marca": marca,
            "unidad": unidad,
            "codigo_barras": datos_texto.get("codigo_barras", ""),
            "costo_referencia": _decimal_o_none(datos_texto.get("costo_referencia", "")) or 0,
            "precio_venta": _decimal_o_none(datos_texto.get("precio_venta", "")) or 0,
            "tasa_itbis": _decimal_o_none(datos_texto.get("tasa_itbis", "")) or 18,
            "stock_minimo_defecto": _decimal_o_none(datos_texto.get("stock_minimo_defecto", "")) or 0,
        }
        filas.append(FilaImportada(numero=numero, crudo=datos_texto, datos=preparados, errores=errores))
    return filas


def reporte_de_errores_csv(filas: list[FilaImportada]) -> str:
    """Arma un CSV con solo las filas que fallaron, para que se puedan corregir y reintentar."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["fila", "nombre", "errores"])
    for fila in filas:
        if not fila.es_valida:
            escritor.writerow([fila.numero, fila.datos.get("nombre", ""), " | ".join(fila.errores)])
    return buffer.getvalue()
