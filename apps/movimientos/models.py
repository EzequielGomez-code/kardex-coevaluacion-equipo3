"""
Modelos de movimientos: tipos configurables, la cabecera y sus líneas, los
lotes, qué lote surtió cada consumo y la existencia agregada.

Tres capas de saldo, cada una con su razón de existir:

``MovimientoLinea``   el libro mayor — verdad histórica, nunca se toca.
``Lote``              saldo consumible por capa de costo.
``Existencia``        saldo agregado por artículo y almacén, denormalizado
                       a propósito: el listado de existencias no puede ser
                       un ``GROUP BY`` sobre miles de líneas en cada carga
                       de página, y la regla de no-negativo necesita una
                       fila real que bloquear con ``select_for_update``.

Una transferencia genera dos líneas por artículo (una ``-1`` en el almacén de
origen, una ``+1`` en el de destino) dentro de un único ``Movimiento``. Esa
decisión hace uniforme todo lo demás: el kardex de un artículo es un filtro
sobre una sola tabla, y la anulación es invertir el signo de sus líneas.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.catalogo.models import Articulo, Cliente, Proveedor
from apps.nucleo.models import Almacen, ModeloConMarcaDeTiempo


class Naturaleza(models.TextChoices):
    """
    Vocabulario cerrado de la aritmética del inventario.

    El usuario configura los *tipos* de movimiento (Compra, Merma, Consumo
    interno…) desde la pantalla; la naturaleza —qué le hace cada uno a la
    existencia— es una de estas cuatro y no se inventa desde la interfaz.
    """

    ENTRADA = "entrada", "Entrada"
    SALIDA = "salida", "Salida"
    TRANSFERENCIA = "transferencia", "Transferencia"
    AJUSTE = "ajuste", "Ajuste"


class EstadoMovimiento(models.TextChoices):
    """Ciclo de vida de un movimiento."""

    BORRADOR = "borrador", "Borrador"
    PENDIENTE = "pendiente", "Pendiente de aprobación"
    CONFIRMADO = "confirmado", "Confirmado"
    RECHAZADO = "rechazado", "Rechazado"
    ANULADO = "anulado", "Anulado"


class TipoMovimiento(ModeloConMarcaDeTiempo):
    """
    Tipo de movimiento configurable: Compra, Devolución, Merma, Ajuste…

    Cada tipo fija su ``naturaleza`` (una de las cuatro operaciones básicas)
    y qué exige al registrarse. La numeración es propia de cada tipo, con su
    prefijo y su contador.
    """

    codigo = models.CharField("código", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=80)
    naturaleza = models.CharField("naturaleza", max_length=20, choices=Naturaleza.choices)
    prefijo_numeracion = models.CharField("prefijo de numeración", max_length=10)
    secuencia_actual = models.PositiveIntegerField("secuencia actual", default=0, editable=False)
    exige_documento = models.BooleanField("exige número de documento", default=False)
    exige_ncf = models.BooleanField("exige comprobante fiscal (NCF)", default=False)
    exige_motivo = models.BooleanField("exige motivo", default=False)
    exige_aprobacion = models.BooleanField("exige aprobación", default=False)
    permite_anulacion = models.BooleanField("permite anulación", default=True)
    tipo_contrapartida = models.ForeignKey(
        "self", on_delete=models.SET_NULL, related_name="tipos_que_lo_anulan",
        verbose_name="tipo de la contrapartida", null=True, blank=True,
        help_text="Con qué tipo se registra la anulación. Vacío = el mismo tipo.",
    )
    color = models.CharField(
        "color", max_length=7, default="#6A665F",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use un color en formato #RRGGBB.")],
    )
    orden = models.PositiveIntegerField("orden", default=10)
    activo = models.BooleanField("activo", default=True)
    es_sistema = models.BooleanField(
        "es del sistema", default=False,
        help_text="Los tipos del sistema no se pueden eliminar.",
    )

    class Meta:
        verbose_name = "tipo de movimiento"
        verbose_name_plural = "tipos de movimiento"
        ordering = ["orden", "codigo"]

    def __str__(self) -> str:
        return self.nombre


class Movimiento(ModeloConMarcaDeTiempo):
    """
    Cabecera de un movimiento de inventario.

    ``naturaleza`` y ``metodo_valoracion`` son copias congeladas: la primera
    del tipo elegido, la segunda del parámetro del sistema en el momento de
    confirmar. Así, si alguien edita el tipo o el parámetro mañana, la
    historia ya registrada no cambia de significado.
    """

    numero = models.CharField("número", max_length=30, unique=True)
    tipo = models.ForeignKey(
        TipoMovimiento, on_delete=models.PROTECT, related_name="movimientos", verbose_name="tipo"
    )
    naturaleza = models.CharField(
        "naturaleza", max_length=20, choices=Naturaleza.choices, editable=False
    )
    estado = models.CharField(
        "estado", max_length=20, choices=EstadoMovimiento.choices,
        default=EstadoMovimiento.BORRADOR,
    )
    fecha = models.DateTimeField("fecha", default=timezone.now)
    almacen_origen = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="movimientos_salida",
        verbose_name="almacén de origen", null=True, blank=True,
    )
    almacen_destino = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="movimientos_entrada",
        verbose_name="almacén de destino", null=True, blank=True,
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, related_name="movimientos",
        verbose_name="proveedor", null=True, blank=True,
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="movimientos",
        verbose_name="cliente", null=True, blank=True,
    )
    documento_tipo = models.CharField("tipo de documento", max_length=20, blank=True)
    documento_numero = models.CharField("número de documento", max_length=40, blank=True)
    ncf = models.CharField(
        "comprobante fiscal (NCF)", max_length=19, blank=True,
        validators=[RegexValidator(r"^[A-Z]\d{10}$", "Formato de NCF inválido.")],
    )
    fecha_documento = models.DateField("fecha del documento", null=True, blank=True)
    motivo = models.TextField("motivo", blank=True)
    observaciones = models.TextField("observaciones", blank=True)
    metodo_valoracion = models.CharField(
        "método de valoración", max_length=30, blank=True, editable=False
    )
    total_cantidad = models.DecimalField(
        "cantidad total", max_digits=18, decimal_places=4, default=0, editable=False
    )
    total_costo = models.DecimalField(
        "costo total", max_digits=18, decimal_places=4, default=0, editable=False
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos",
        verbose_name="usuario",
    )
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="movimientos_aprobados",
        verbose_name="aprobado por", null=True, blank=True,
    )
    aprobado_en = models.DateTimeField("aprobado en", null=True, blank=True)
    anula = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="anulaciones",
        verbose_name="anula al movimiento", null=True, blank=True,
    )
    anulado_en = models.DateTimeField("anulado en", null=True, blank=True)
    motivo_anulacion = models.TextField("motivo de la anulación", blank=True)
    lineas_solicitadas = models.JSONField(
        "líneas solicitadas", default=list, blank=True,
        help_text=(
            "Lo que se pidió registrar, mientras el movimiento espera aprobación. "
            "Las líneas reales (Lote, ConsumoLote, Existencia) solo existen para "
            "movimientos confirmados; esto es la intención, no el efecto."
        ),
    )

    class Meta:
        verbose_name = "movimiento"
        verbose_name_plural = "movimientos"
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["numero"], name="movimiento_numero_unico"),
            models.UniqueConstraint(fields=["anula"], name="un_movimiento_se_anula_una_vez"),
            models.UniqueConstraint(
                fields=["proveedor", "ncf"], condition=~models.Q(ncf=""),
                name="ncf_unico_por_proveedor",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(naturaleza=Naturaleza.ENTRADA, almacen_origen__isnull=True,
                            almacen_destino__isnull=False)
                    | models.Q(naturaleza=Naturaleza.SALIDA, almacen_origen__isnull=False,
                              almacen_destino__isnull=True)
                    | models.Q(naturaleza=Naturaleza.TRANSFERENCIA, almacen_origen__isnull=False,
                              almacen_destino__isnull=False)
                    | models.Q(naturaleza=Naturaleza.AJUSTE)
                ),
                name="movimiento_almacenes_coherentes",
            ),
        ]
        indexes = [
            models.Index(fields=["estado", "-fecha"], name="movimiento_estado_fecha_idx"),
            models.Index(fields=["almacen_origen", "-fecha"], name="movimiento_origen_idx"),
            models.Index(fields=["almacen_destino", "-fecha"], name="movimiento_destino_idx"),
            models.Index(fields=["tipo", "-fecha"], name="movimiento_tipo_fecha_idx"),
        ]

    def __str__(self) -> str:
        return self.numero

    def save(self, *args, **kwargs):
        """
        Guarda el movimiento, protegiendo la inmutabilidad de lo confirmado.

        Un movimiento ``CONFIRMADO`` o ``ANULADO`` no se puede volver a
        escribir salvo el juego de campos que usa la propia anulación
        (idéntico criterio al de ``RegistroAuditoria``: inmutable no es
        indiferente, es una decisión deliberada del diseño).
        """
        if self.pk is not None:
            anterior = Movimiento.objects.filter(pk=self.pk).values_list("estado", flat=True).first()
            if anterior in (EstadoMovimiento.CONFIRMADO, EstadoMovimiento.ANULADO):
                campos_permitidos = {
                    "estado", "anulado_en", "motivo_anulacion", "actualizado_en",
                    "aprobado_por", "aprobado_en",
                }
                update_fields = kwargs.get("update_fields")
                if update_fields is None or not set(update_fields) <= campos_permitidos:
                    raise ValueError(
                        "Un movimiento confirmado no se edita ni se elimina; "
                        "regístrese un ajuste o una anulación."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impide borrar un movimiento que ya salió de borrador."""
        if self.estado != EstadoMovimiento.BORRADOR:
            raise ValueError("Solo un movimiento en borrador se puede eliminar.")
        super().delete(*args, **kwargs)


class MovimientoLinea(models.Model):
    """
    Línea de movimiento: el libro mayor del kardex.

    ``signo`` es ``+1`` para lo que entra a la existencia y ``-1`` para lo
    que sale; ``cantidad`` siempre viaja positiva. ``costo_total`` es la
    suma de lo que cuesta cada capa de lote consumida, nunca
    ``cantidad × promedio`` — esa distinción es la que evita que el valor
    del inventario derive con el uso.
    """

    movimiento = models.ForeignKey(
        Movimiento, on_delete=models.CASCADE, related_name="lineas", verbose_name="movimiento"
    )
    articulo = models.ForeignKey(
        Articulo, on_delete=models.PROTECT, related_name="lineas", verbose_name="artículo"
    )
    almacen = models.ForeignKey(Almacen, on_delete=models.PROTECT, verbose_name="almacén")
    signo = models.SmallIntegerField("signo")
    cantidad = models.DecimalField("cantidad", max_digits=18, decimal_places=4)
    costo_unitario = models.DecimalField("costo unitario", max_digits=18, decimal_places=4)
    costo_total = models.DecimalField("costo total", max_digits=18, decimal_places=4)
    saldo_posterior = models.DecimalField(
        "saldo posterior", max_digits=18, decimal_places=4,
        help_text="Foto del saldo del artículo en este almacén justo después de esta línea.",
    )
    notas = models.CharField("notas", max_length=250, blank=True)

    class Meta:
        verbose_name = "línea de movimiento"
        verbose_name_plural = "líneas de movimiento"
        ordering = ["movimiento_id", "id"]
        indexes = [
            models.Index(fields=["articulo", "almacen", "id"], name="linea_kardex_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0), name="linea_cantidad_positiva"
            ),
            models.CheckConstraint(
                condition=models.Q(signo__in=[-1, 1]), name="linea_signo_valido"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movimiento.numero} · {self.articulo.sku} · {self.cantidad}"


class Lote(ModeloConMarcaDeTiempo):
    """Capa de costo: una entrada concreta, con su costo y lo que queda de ella."""

    codigo = models.CharField("código", max_length=30)
    numero_proveedor = models.CharField("número del proveedor", max_length=40, blank=True)
    articulo = models.ForeignKey(
        Articulo, on_delete=models.PROTECT, related_name="lotes", verbose_name="artículo"
    )
    almacen = models.ForeignKey(Almacen, on_delete=models.PROTECT, verbose_name="almacén")
    linea_origen = models.ForeignKey(
        MovimientoLinea, on_delete=models.PROTECT, related_name="lotes_creados",
        verbose_name="línea de origen",
    )
    costo_unitario = models.DecimalField("costo unitario", max_digits=18, decimal_places=4)
    cantidad_inicial = models.DecimalField("cantidad inicial", max_digits=18, decimal_places=4)
    cantidad_disponible = models.DecimalField(
        "cantidad disponible", max_digits=18, decimal_places=4
    )
    recibido_en = models.DateTimeField("recibido en", default=timezone.now)
    fecha_vencimiento = models.DateField("fecha de vencimiento", null=True, blank=True)

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        ordering = ["recibido_en", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["almacen", "codigo"], name="lote_codigo_unico_por_almacen"
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad_disponible__gte=0), name="lote_no_negativo"
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad_disponible__lte=models.F("cantidad_inicial")),
                name="lote_no_excede_su_inicial",
            ),
        ]
        indexes = [
            models.Index(
                fields=["articulo", "almacen", "recibido_en", "id"],
                name="lote_peps_idx",
                condition=models.Q(cantidad_disponible__gt=0),
            ),
            models.Index(
                fields=["fecha_vencimiento"], name="lote_vencimiento_idx",
                condition=models.Q(fecha_vencimiento__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} ({self.articulo.sku} en {self.almacen.codigo})"

    @property
    def agotado(self) -> bool:
        """Indica si ya no queda cantidad disponible en este lote."""
        return self.cantidad_disponible <= 0


class ConsumoLote(models.Model):
    """De qué lote salió cada unidad de una línea de movimiento."""

    linea = models.ForeignKey(
        MovimientoLinea, on_delete=models.CASCADE, related_name="consumos", verbose_name="línea"
    )
    lote = models.ForeignKey(
        Lote, on_delete=models.PROTECT, related_name="consumos", verbose_name="lote",
        null=True, blank=True,
        help_text="Vacío cuando la salida se valoró sin respaldo de lote (existencia negativa).",
    )
    cantidad = models.DecimalField("cantidad", max_digits=18, decimal_places=4)
    costo_unitario = models.DecimalField("costo unitario", max_digits=18, decimal_places=4)

    class Meta:
        verbose_name = "consumo de lote"
        verbose_name_plural = "consumos de lote"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["lote"], name="consumo_lote_idx"),
            models.Index(fields=["linea"], name="consumo_linea_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="consumo_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.linea} ← {self.lote or 'sin lote'} ({self.cantidad})"


class Existencia(ModeloConMarcaDeTiempo):
    """
    Saldo agregado de un artículo en un almacén.

    ``valor`` es ``Σ(disponible × costo)`` de los lotes vivos, guardado
    explícito y no derivado de ``cantidad × costo_promedio`` — así el reporte
    de valorización cuadra exacto, sin arrastrar redondeos.
    """

    articulo = models.ForeignKey(
        Articulo, on_delete=models.CASCADE, related_name="existencias", verbose_name="artículo"
    )
    almacen = models.ForeignKey(
        Almacen, on_delete=models.CASCADE, related_name="existencias", verbose_name="almacén"
    )
    cantidad = models.DecimalField("cantidad", max_digits=18, decimal_places=4, default=0)
    valor = models.DecimalField("valor", max_digits=18, decimal_places=4, default=0)
    stock_minimo = models.DecimalField(
        "existencia mínima", max_digits=18, decimal_places=4, default=0
    )
    stock_maximo = models.DecimalField(
        "existencia máxima", max_digits=18, decimal_places=4, null=True, blank=True
    )
    punto_reorden = models.DecimalField(
        "punto de reorden", max_digits=18, decimal_places=4, null=True, blank=True
    )
    ubicacion = models.CharField("ubicación física", max_length=40, blank=True)
    ultimo_movimiento_en = models.DateTimeField("último movimiento", null=True, blank=True)

    class Meta:
        verbose_name = "existencia"
        verbose_name_plural = "existencias"
        ordering = ["almacen", "articulo"]
        constraints = [
            # Sin CheckConstraint de no-negativo a propósito: «permitir_stock_negativo»
            # es un parámetro que se edita en caliente desde la pantalla, y una
            # restricción estática de base no puede depender de él. La regla la
            # aplica el servicio (ver ServicioMovimientos._aplicar_linea_salida).
            models.UniqueConstraint(fields=["articulo", "almacen"], name="existencia_unica"),
        ]
        indexes = [
            models.Index(fields=["almacen", "cantidad"], name="existencia_almacen_cant_idx"),
            models.Index(fields=["ultimo_movimiento_en"], name="existencia_ultimo_mov_idx"),
            models.Index(fields=["almacen", "stock_minimo"], name="existencia_minimo_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.articulo.sku} en {self.almacen.codigo}: {self.cantidad}"

    @property
    def costo_promedio(self) -> Decimal:
        """Costo promedio derivado: ``valor / cantidad``, o cero sin existencia."""
        if not self.cantidad:
            return Decimal("0")
        return self.valor / self.cantidad

    @property
    def bajo_minimo(self) -> bool:
        """Indica si la existencia está por debajo del mínimo configurado."""
        return self.cantidad < self.stock_minimo
