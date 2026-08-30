"""
Modelos de configuración: la capa que hace personalizable a Kardex.

Cada tabla de este módulo convierte una decisión de negocio en datos editables
desde la interfaz. Agregar un campo a un producto, cambiar la moneda o exigir
la aprobación de un gerente no requiere tocar el código ni desplegar de nuevo.

``DefinicionCampo`` y ``ValorCampo`` son genéricos a propósito: se cuelgan de
cualquier modelo mediante ``entidad`` (texto) + ``objeto_id``, sin llaves
foráneas. Así catálogo, movimientos y alertas los usan sin que ninguna de esas
apps tenga que modificar esta.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.validators import RegexValidator
from django.db import models

from apps.nucleo.models import ModeloConMarcaDeTiempo

VALIDADOR_CLAVE = RegexValidator(
    r"^[a-z][a-z0-9_]*$",
    "Use minúsculas, números y guion bajo; debe empezar con una letra.",
)


class TipoDato(models.TextChoices):
    """Tipos que puede tomar un parámetro o un campo personalizado."""

    TEXTO = "texto", "Texto"
    NUMERO = "numero", "Número entero"
    DECIMAL = "decimal", "Número decimal"
    FECHA = "fecha", "Fecha"
    BOOLEANO = "booleano", "Sí / No"
    LISTA = "lista", "Lista de opciones"
    LISTA_MULTIPLE = "lista_multiple", "Lista de opciones (múltiple)"
    USUARIO = "usuario", "Usuario del sistema"
    ARCHIVO = "archivo", "Archivo"


class Parametro(ModeloConMarcaDeTiempo):
    """
    Parámetro global del sistema, editable desde «Parámetros del sistema».

    Ejemplos: ``moneda``, ``formato_sku``, ``permitir_stock_negativo``,
    ``metodo_valoracion``, ``dias_sin_movimiento``, ``zona_horaria``.
    """

    clave = models.CharField("clave", max_length=60, unique=True, validators=[VALIDADOR_CLAVE])
    valor = models.TextField("valor", blank=True)
    tipo = models.CharField(
        "tipo", max_length=20, choices=TipoDato.choices, default=TipoDato.TEXTO
    )
    etiqueta = models.CharField("etiqueta", max_length=120)
    grupo = models.CharField("grupo", max_length=60, default="General", db_index=True)
    editable = models.BooleanField(
        "editable",
        default=True,
        help_text="Si está apagado, solo se cambia por migración o comando.",
    )
    ayuda = models.CharField("texto de ayuda", max_length=250, blank=True)
    opciones = models.JSONField("opciones", default=list, blank=True)
    orden = models.PositiveIntegerField("orden", default=100)

    class Meta:
        verbose_name = "parámetro"
        verbose_name_plural = "parámetros"
        ordering = ["grupo", "orden", "clave"]

    def __str__(self) -> str:
        return f"{self.clave} = {self.valor}"

    def valor_convertido(self) -> Any:
        """Devuelve el valor ya convertido al tipo declarado."""
        if self.tipo == TipoDato.BOOLEANO:
            return str(self.valor).strip().lower() in {"1", "true", "si", "sí", "verdadero"}
        if self.tipo == TipoDato.NUMERO:
            try:
                return int(self.valor)
            except (TypeError, ValueError):
                return 0
        if self.tipo == TipoDato.DECIMAL:
            try:
                return Decimal(self.valor)
            except (InvalidOperation, TypeError, ValueError):
                return Decimal("0")
        if self.tipo == TipoDato.LISTA_MULTIPLE:
            return [parte.strip() for parte in str(self.valor).split(",") if parte.strip()]
        return self.valor


class DefinicionCampo(ModeloConMarcaDeTiempo):
    """
    Definición de un campo personalizado que el usuario agrega desde la interfaz.

    ``entidad`` es el nombre lógico del modelo al que se cuelga (``Articulo``,
    ``Movimiento``, ``Proveedor``…). ``categoria`` permite que un campo aplique
    solo a una categoría de artículos y no a todas.
    """

    entidad = models.CharField("entidad", max_length=60, db_index=True)
    categoria = models.CharField(
        "categoría",
        max_length=60,
        blank=True,
        help_text="Vacío = aplica a todos los registros de la entidad.",
    )
    clave = models.CharField("clave", max_length=60, validators=[VALIDADOR_CLAVE])
    etiqueta = models.CharField("etiqueta", max_length=120)
    tipo = models.CharField("tipo", max_length=20, choices=TipoDato.choices)
    requerido = models.BooleanField("requerido", default=False)
    orden = models.PositiveIntegerField("orden", default=100)
    opciones = models.JSONField(
        "opciones",
        default=list,
        blank=True,
        help_text="Lista de valores para los tipos lista y lista múltiple.",
    )
    ayuda = models.CharField("texto de ayuda", max_length=250, blank=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "definición de campo"
        verbose_name_plural = "definiciones de campo"
        ordering = ["entidad", "orden", "clave"]
        constraints = [
            models.UniqueConstraint(
                fields=["entidad", "categoria", "clave"],
                name="campo_unico_por_entidad_y_categoria",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entidad}.{self.clave}"

    @property
    def es_de_opciones(self) -> bool:
        """Indica si el tipo del campo se alimenta de una lista de opciones."""
        return self.tipo in {TipoDato.LISTA, TipoDato.LISTA_MULTIPLE}


class ValorCampo(models.Model):
    """
    Valor concreto de un campo personalizado para un objeto.

    Se usan columnas separadas por tipo en vez de una sola de texto, para poder
    filtrar y ordenar por número o por fecha sin convertir en cada consulta.
    Los tipos ``lista_multiple``, ``usuario`` y ``archivo`` se guardan en
    ``valor_texto`` (lista separada por comas, id del usuario, ruta del archivo).
    """

    definicion = models.ForeignKey(
        DefinicionCampo,
        on_delete=models.CASCADE,
        related_name="valores",
        verbose_name="definición",
    )
    objeto_id = models.CharField("id del objeto", max_length=40, db_index=True)
    valor_texto = models.TextField("valor de texto", blank=True)
    valor_numero = models.DecimalField(
        "valor numérico", max_digits=18, decimal_places=4, null=True, blank=True
    )
    valor_fecha = models.DateField("valor de fecha", null=True, blank=True)
    valor_bool = models.BooleanField("valor booleano", null=True, blank=True)

    class Meta:
        verbose_name = "valor de campo"
        verbose_name_plural = "valores de campo"
        constraints = [
            models.UniqueConstraint(
                fields=["definicion", "objeto_id"], name="valor_unico_por_objeto"
            ),
        ]
        indexes = [
            models.Index(fields=["objeto_id"], name="valorcampo_objeto_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.definicion} [{self.objeto_id}]"

    @property
    def valor(self) -> Any:
        """Devuelve el valor guardado en la columna que corresponde al tipo."""
        tipo = self.definicion.tipo
        if tipo == TipoDato.BOOLEANO:
            return self.valor_bool
        if tipo in {TipoDato.NUMERO, TipoDato.DECIMAL}:
            if self.valor_numero is None:
                return None
            return int(self.valor_numero) if tipo == TipoDato.NUMERO else self.valor_numero
        if tipo == TipoDato.FECHA:
            return self.valor_fecha
        if tipo == TipoDato.LISTA_MULTIPLE:
            return [parte for parte in self.valor_texto.split(",") if parte]
        return self.valor_texto


class Etiqueta(ModeloConMarcaDeTiempo):
    """Etiqueta de color que se puede pegar a cualquier objeto del sistema."""

    nombre = models.CharField("nombre", max_length=60, unique=True)
    color = models.CharField(
        "color",
        max_length=7,
        default="#6A665F",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use un color en formato #RRGGBB.")],
    )
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "etiqueta"
        verbose_name_plural = "etiquetas"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class EtiquetaObjeto(models.Model):
    """Relación entre una etiqueta y cualquier objeto, identificado por entidad + id."""

    etiqueta = models.ForeignKey(
        Etiqueta, on_delete=models.CASCADE, related_name="asignaciones", verbose_name="etiqueta"
    )
    entidad = models.CharField("entidad", max_length=60, db_index=True)
    objeto_id = models.CharField("id del objeto", max_length=40, db_index=True)

    class Meta:
        verbose_name = "etiqueta de objeto"
        verbose_name_plural = "etiquetas de objeto"
        constraints = [
            models.UniqueConstraint(
                fields=["etiqueta", "entidad", "objeto_id"], name="etiqueta_objeto_unica"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.etiqueta} → {self.entidad}#{self.objeto_id}"


class VistaGuardada(ModeloConMarcaDeTiempo):
    """
    Combinación de filtros, columnas y orden que un usuario guarda para
    reutilizarla. Si ``compartida`` está encendida, la ven todos.
    """

    usuario = models.ForeignKey(
        "nucleo.Usuario",
        on_delete=models.CASCADE,
        related_name="vistas_guardadas",
        verbose_name="usuario",
    )
    nombre = models.CharField("nombre", max_length=100)
    entidad = models.CharField("entidad", max_length=60, db_index=True)
    filtros = models.JSONField("filtros", default=dict, blank=True)
    columnas = models.JSONField("columnas", default=list, blank=True)
    orden = models.CharField("orden", max_length=60, blank=True)
    compartida = models.BooleanField("compartida", default=False)
    por_defecto = models.BooleanField("por defecto", default=False)

    class Meta:
        verbose_name = "vista guardada"
        verbose_name_plural = "vistas guardadas"
        ordering = ["entidad", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "entidad", "nombre"], name="vista_unica_por_usuario"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.entidad})"


class FlujoAprobacion(ModeloConMarcaDeTiempo):
    """
    Regla que obliga a que un rol apruebe una operación cuando se cumple una
    condición. La condición se guarda como JSON para no fijar en el código qué
    se puede evaluar.

    Ejemplo: ``{"campo": "total", "operador": ">", "valor": 50000}``.
    """

    nombre = models.CharField("nombre", max_length=120)
    entidad = models.CharField("entidad", max_length=60, db_index=True)
    condicion = models.JSONField("condición", default=dict, blank=True)
    rol_aprobador = models.ForeignKey(
        "nucleo.Rol",
        on_delete=models.PROTECT,
        related_name="flujos_aprobacion",
        verbose_name="rol aprobador",
    )
    orden = models.PositiveIntegerField("orden", default=1)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "flujo de aprobación"
        verbose_name_plural = "flujos de aprobación"
        ordering = ["entidad", "orden"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.entidad})"


class PlantillaNotificacion(ModeloConMarcaDeTiempo):
    """Texto de una notificación, editable sin desplegar."""

    class Canal(models.TextChoices):
        """Medios por los que se puede enviar una notificación."""

        SISTEMA = "sistema", "En el sistema"
        CORREO = "correo", "Correo electrónico"

    clave = models.CharField("clave", max_length=60, unique=True, validators=[VALIDADOR_CLAVE])
    asunto = models.CharField("asunto", max_length=200)
    cuerpo = models.TextField("cuerpo")
    canal = models.CharField(
        "canal", max_length=20, choices=Canal.choices, default=Canal.SISTEMA
    )
    variables = models.JSONField(
        "variables",
        default=list,
        blank=True,
        help_text="Nombres disponibles en la plantilla, por ejemplo: articulo, almacen.",
    )
    activa = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "plantilla de notificación"
        verbose_name_plural = "plantillas de notificación"
        ordering = ["clave"]

    def __str__(self) -> str:
        return self.clave


class MapeoImportacion(ModeloConMarcaDeTiempo):
    """Correspondencia entre las columnas de un archivo y los campos del sistema."""

    nombre = models.CharField("nombre", max_length=120)
    entidad = models.CharField("entidad", max_length=60, db_index=True)
    mapeo_columnas = models.JSONField("mapeo de columnas", default=dict, blank=True)
    usuario = models.ForeignKey(
        "nucleo.Usuario",
        on_delete=models.SET_NULL,
        related_name="mapeos_importacion",
        verbose_name="usuario",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "mapeo de importación"
        verbose_name_plural = "mapeos de importación"
        ordering = ["entidad", "nombre"]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.entidad})"
