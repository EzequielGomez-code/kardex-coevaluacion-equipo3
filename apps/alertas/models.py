"""
Modelos de Alertas: reglas configurables y las alertas que generan.

``ReglaAlerta`` es configuración; ``Alerta`` es cada ocurrencia detectada.
La idempotencia — no duplicar la misma alerta abierta dos veces — la
garantiza la base con una restricción única parcial (solo entre alertas
abiertas o en proceso), no el código del evaluador.
"""

from __future__ import annotations

from django.db import models

from apps.catalogo.models import Articulo, Categoria
from apps.nucleo.models import Almacen, ModeloConMarcaDeTiempo


class TipoRegla(models.TextChoices):
    """Condiciones que una regla puede vigilar. Vocabulario cerrado."""

    STOCK_BAJO = "stock_bajo", "Existencia por debajo del mínimo"
    STOCK_CERO = "stock_cero", "Existencia en cero"
    SIN_MOVIMIENTO = "sin_movimiento", "Sin movimiento reciente"
    VENCIMIENTO_PROXIMO = "vencimiento_proximo", "Lote por vencer"


class EstadoAlerta(models.TextChoices):
    """Ciclo de vida de una alerta."""

    ABIERTA = "abierta", "Abierta"
    EN_PROCESO = "en_proceso", "En proceso"
    RESUELTA = "resuelta", "Resuelta"
    IGNORADA = "ignorada", "Ignorada"


class ReglaAlerta(ModeloConMarcaDeTiempo):
    """
    Regla configurable: qué vigilar, dónde y con qué margen.

    Sin almacenes ni categorías asociadas, la regla aplica a todos — así una
    ferretería con un solo almacén no está obligada a elegir uno.
    """

    nombre = models.CharField("nombre", max_length=120)
    tipo = models.CharField("tipo", max_length=20, choices=TipoRegla.choices)
    dias_umbral = models.PositiveIntegerField(
        "días de margen", null=True, blank=True,
        help_text="Días sin movimiento, o días de antelación antes de vencer. "
                  "No aplica a las reglas de existencia.",
    )
    almacenes = models.ManyToManyField(
        Almacen, verbose_name="almacenes", blank=True,
        help_text="Vacío = todos los almacenes.",
    )
    categorias = models.ManyToManyField(
        Categoria, verbose_name="categorías", blank=True,
        help_text="Vacío = todas las categorías.",
    )
    activa = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "regla de alerta"
        verbose_name_plural = "reglas de alerta"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Alerta(ModeloConMarcaDeTiempo):
    """
    Una ocurrencia detectada de una regla, sobre un artículo en un almacén.

    ``almacen`` es obligatorio a propósito: con NULL la restricción única de
    abajo no deduplicaría entre almacenes distintos (NULL nunca es igual a
    NULL en una restricción única de SQL).
    """

    regla = models.ForeignKey(
        ReglaAlerta, on_delete=models.CASCADE, related_name="alertas", verbose_name="regla"
    )
    articulo = models.ForeignKey(
        Articulo, on_delete=models.CASCADE, related_name="alertas", verbose_name="artículo"
    )
    almacen = models.ForeignKey(Almacen, on_delete=models.CASCADE, verbose_name="almacén")
    estado = models.CharField(
        "estado", max_length=20, choices=EstadoAlerta.choices, default=EstadoAlerta.ABIERTA,
    )
    mensaje = models.CharField("mensaje", max_length=250)
    contexto = models.JSONField(
        "contexto", default=dict, blank=True,
        help_text="Los valores que dispararon la alerta (cantidad, umbral, días…).",
    )
    generada_en = models.DateTimeField("generada en", auto_now_add=True)
    resuelta_en = models.DateTimeField("resuelta en", null=True, blank=True)
    resuelta_por = models.ForeignKey(
        "nucleo.Usuario", on_delete=models.SET_NULL, related_name="alertas_resueltas",
        verbose_name="resuelta por", null=True, blank=True,
    )

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["-generada_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["regla", "articulo", "almacen"],
                condition=models.Q(estado__in=[EstadoAlerta.ABIERTA, EstadoAlerta.EN_PROCESO]),
                name="alerta_abierta_unica_por_regla_articulo_almacen",
            ),
        ]
        indexes = [
            models.Index(fields=["estado", "-generada_en"], name="alerta_estado_fecha_idx"),
            models.Index(fields=["articulo", "almacen"], name="alerta_articulo_almacen_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.mensaje} ({self.articulo.sku})"
