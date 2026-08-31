"""
Modelos del catálogo: categorías, marcas, unidades de medida, artículos,
proveedores y clientes.

El árbol de categorías se modela con ``padre`` (FK) más una ``ruta``
materializada (``"0020.0010"``, un segmento de 4 dígitos por nivel, que
codifica el orden) en vez de una librería externa: con eso, el árbol
completo, los descendientes de un nodo y los artículos de una categoría y sus
hijas salen de una sola consulta indexada por ``ruta``.
"""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models

from apps.catalogo.validadores import normalizar_rnc, validar_rnc
from apps.nucleo.models import ModeloConMarcaDeTiempo

VALIDADOR_CODIGO = RegexValidator(
    r"^[A-Z0-9_-]+$", "Use mayúsculas, números, guiones y guion bajo."
)


class Categoria(ModeloConMarcaDeTiempo):
    """
    Categoría de artículos, organizada en árbol.

    ``ruta`` es el camino completo desde la raíz, con un segmento de 4
    dígitos por nivel (``"0020.0010.0030"``); ordenar por ``ruta`` pinta el
    árbol completo en el orden correcto sin necesidad de recorrerlo en
    Python, y ``ruta__startswith`` resuelve "esta categoría y sus hijas" en
    un solo filtro.
    """

    codigo = models.CharField(
        "código", max_length=30, validators=[VALIDADOR_CODIGO]
    )  # único por padre, no global: ver constraint categoria_codigo_unico_por_padre
    nombre = models.CharField("nombre", max_length=120)
    descripcion = models.CharField("descripción", max_length=250, blank=True)
    padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="hijas",
        verbose_name="categoría padre",
        null=True,
        blank=True,
    )
    ruta = models.CharField("ruta", max_length=64, unique=True, editable=False)
    nivel = models.PositiveSmallIntegerField("nivel", default=0, editable=False)
    orden = models.PositiveIntegerField("orden", default=10)
    secuencia_sku = models.PositiveIntegerField(
        "secuencia del SKU",
        default=0,
        editable=False,
        help_text="Contador interno para generar el SKU de los artículos de esta categoría.",
    )
    icono = models.CharField("ícono", max_length=30, blank=True, default="catalogo")
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["ruta"]
        constraints = [
            models.UniqueConstraint(
                fields=["padre", "codigo"], name="categoria_codigo_unico_por_padre"
            ),
            models.CheckConstraint(
                condition=models.Q(nivel__lte=5), name="categoria_profundidad_maxima"
            ),
        ]
        indexes = [
            models.Index(fields=["ruta"], name="categoria_ruta_idx"),
            models.Index(fields=["activo", "ruta"], name="categoria_activa_idx"),
        ]

    def __str__(self) -> str:
        return self.nombre

    @property
    def es_raiz(self) -> bool:
        """Indica si la categoría no tiene padre."""
        return self.padre_id is None


class Marca(ModeloConMarcaDeTiempo):
    """Marca comercial de un artículo."""

    nombre = models.CharField("nombre", max_length=120, unique=True)
    pais = models.CharField("país", max_length=60, blank=True)
    sitio_web = models.URLField("sitio web", blank=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class UnidadMedida(ModeloConMarcaDeTiempo):
    """Unidad en la que se cuenta un artículo: unidad, saco, quintal, metro…"""

    codigo = models.CharField("código", max_length=10, unique=True)
    nombre = models.CharField("nombre", max_length=60)
    simbolo = models.CharField("símbolo", max_length=10, blank=True)
    permite_decimales = models.BooleanField(
        "permite decimales",
        default=True,
        help_text="Si está apagado, la cantidad de esta unidad siempre es un entero.",
    )
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "unidad de medida"
        verbose_name_plural = "unidades de medida"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nombre}"

    def save(self, *args, **kwargs) -> None:
        """Guarda el código de la unidad siempre en mayúsculas."""
        self.codigo = self.codigo.upper()
        super().save(*args, **kwargs)


class Articulo(ModeloConMarcaDeTiempo):
    """Producto del catálogo: lo que se compra, se guarda y se vende."""

    sku = models.CharField("SKU", max_length=40, unique=True)
    codigo_barras = models.CharField("código de barras", max_length=20, blank=True)
    nombre = models.CharField("nombre", max_length=200)
    descripcion = models.TextField("descripción", blank=True)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="articulos", verbose_name="categoría"
    )
    marca = models.ForeignKey(
        Marca,
        on_delete=models.SET_NULL,
        related_name="articulos",
        verbose_name="marca",
        null=True,
        blank=True,
    )
    unidad = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT, related_name="articulos", verbose_name="unidad"
    )
    es_inventariable = models.BooleanField(
        "controla existencia",
        default=True,
        help_text="Si está apagado, el artículo no lleva kardex (por ejemplo, un servicio).",
    )
    maneja_lotes = models.BooleanField("maneja lotes", default=True)
    maneja_vencimiento = models.BooleanField("maneja vencimiento", default=False)
    costo_referencia = models.DecimalField(
        "costo de referencia", max_digits=18, decimal_places=4, default=0
    )
    precio_venta = models.DecimalField(
        "precio de venta", max_digits=18, decimal_places=4, default=0
    )
    tasa_itbis = models.DecimalField("tasa de ITBIS (%)", max_digits=5, decimal_places=2, default=18)
    stock_minimo_defecto = models.DecimalField(
        "existencia mínima por defecto", max_digits=18, decimal_places=4, default=5
    )
    imagen = models.ImageField("imagen", upload_to="articulos/", blank=True, null=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["codigo_barras"],
                condition=~models.Q(codigo_barras=""),
                name="articulo_codigo_barras_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["nombre"], name="articulo_nombre_idx"),
            models.Index(fields=["categoria", "activo"], name="articulo_categoria_idx"),
            models.Index(fields=["activo", "sku"], name="articulo_activo_sku_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.nombre}"


class Tercero(ModeloConMarcaDeTiempo):
    """
    Base compartida por proveedores y clientes.

    Es una base abstracta y no herencia multitabla a propósito: con MTI,
    cada consulta de :class:`Proveedor` o :class:`Cliente` arrastraría un
    ``JOIN`` contra una tabla común sin necesidad real, porque ningún reporte
    de este sistema mezcla proveedores y clientes en una sola lista.
    """

    class TipoDocumento(models.TextChoices):
        """Tipo del documento de identificación fiscal."""

        RNC = "rnc", "RNC"
        CEDULA = "cedula", "Cédula"
        PASAPORTE = "pasaporte", "Pasaporte"

    codigo = models.CharField("código", max_length=20, unique=True)
    razon_social = models.CharField("razón social", max_length=200)
    nombre_comercial = models.CharField("nombre comercial", max_length=200, blank=True)
    tipo_documento = models.CharField(
        "tipo de documento", max_length=20, choices=TipoDocumento.choices,
        default=TipoDocumento.RNC,
    )
    rnc = models.CharField("RNC o cédula", max_length=13, blank=True)
    telefono = models.CharField("teléfono", max_length=30, blank=True)
    email = models.EmailField("correo electrónico", blank=True)
    direccion = models.CharField("dirección", max_length=250, blank=True)
    contacto = models.CharField("persona de contacto", max_length=120, blank=True)
    dias_credito = models.PositiveIntegerField("días de crédito", default=0)
    limite_credito = models.DecimalField(
        "límite de crédito", max_digits=18, decimal_places=2, default=0
    )
    notas = models.TextField("notas", blank=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        abstract = True
        ordering = ["razon_social"]

    def __str__(self) -> str:
        return self.nombre_comercial or self.razon_social

    def save(self, *args, **kwargs) -> None:
        """Normaliza el RNC a solo dígitos antes de guardar."""
        if self.tipo_documento == self.TipoDocumento.RNC:
            self.rnc = normalizar_rnc(self.rnc)
        super().save(*args, **kwargs)

    def clean(self) -> None:
        """Valida el dígito de control del RNC si el tipo de documento es RNC."""
        super().clean()
        if self.tipo_documento == self.TipoDocumento.RNC and self.rnc:
            validar_rnc(self.rnc)


class Proveedor(Tercero):
    """Suplidor de artículos."""

    class Meta(Tercero.Meta):
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        constraints = [
            models.UniqueConstraint(
                fields=["rnc"], condition=~models.Q(rnc=""), name="proveedor_rnc_unico"
            ),
        ]


class Cliente(Tercero):
    """Comprador de artículos."""

    class Meta(Tercero.Meta):
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        constraints = [
            models.UniqueConstraint(
                fields=["rnc"], condition=~models.Q(rnc=""), name="cliente_rnc_unico"
            ),
        ]


class ProveedorArticulo(ModeloConMarcaDeTiempo):
    """Qué proveedor surte qué artículo, y a qué precio."""

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.CASCADE,
        related_name="articulos_suministrados",
        verbose_name="proveedor",
    )
    articulo = models.ForeignKey(
        Articulo, on_delete=models.CASCADE, related_name="proveedores", verbose_name="artículo"
    )
    codigo_proveedor = models.CharField("código del proveedor", max_length=40, blank=True)
    precio_compra = models.DecimalField("precio de compra", max_digits=18, decimal_places=4)
    tiempo_entrega_dias = models.PositiveIntegerField("tiempo de entrega (días)", default=0)
    cantidad_minima = models.DecimalField(
        "cantidad mínima de pedido", max_digits=18, decimal_places=4, default=1
    )
    es_preferido = models.BooleanField("proveedor preferido", default=False)
    ultima_compra = models.DateField("última compra", null=True, blank=True)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "proveedor de artículo"
        verbose_name_plural = "proveedores de artículo"
        ordering = ["articulo", "-es_preferido"]
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "articulo"], name="proveedor_articulo_unico"
            ),
            models.UniqueConstraint(
                fields=["articulo"],
                condition=models.Q(es_preferido=True),
                name="un_solo_proveedor_preferido_por_articulo",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.proveedor} → {self.articulo}"
