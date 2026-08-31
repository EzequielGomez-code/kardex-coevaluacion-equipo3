"""Formularios de Alertas."""

from __future__ import annotations

from django import forms

from apps.alertas.models import EstadoAlerta, TipoRegla
from apps.catalogo.models import Categoria
from apps.nucleo.forms import MezclaEstilos
from apps.nucleo.models import Almacen

TIPOS_CON_DIAS = {TipoRegla.SIN_MOVIMIENTO, TipoRegla.VENCIMIENTO_PROXIMO}


class FormularioReglaAlerta(MezclaEstilos, forms.Form):
    """Alta y edición de una regla de alerta."""

    nombre = forms.CharField(label="Nombre", max_length=120)
    tipo = forms.ChoiceField(label="Tipo", choices=TipoRegla.choices)
    dias_umbral = forms.IntegerField(
        label="Días de margen", required=False, min_value=1,
        help_text="Solo para «sin movimiento» y «lote por vencer».",
    )
    almacenes = forms.ModelMultipleChoiceField(
        label="Almacenes", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
        required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Vacío = todos los almacenes.",
    )
    categorias = forms.ModelMultipleChoiceField(
        label="Categorías", queryset=Categoria.objects.filter(activo=True).order_by("ruta"),
        required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Vacío = todas las categorías.",
    )
    activa = forms.BooleanField(label="Regla activa", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()

    def clean(self) -> dict:
        """Exige días de margen para los tipos que lo necesitan."""
        datos = super().clean()
        if datos.get("tipo") in TIPOS_CON_DIAS and not datos.get("dias_umbral"):
            self.add_error("dias_umbral", "Este tipo de regla necesita días de margen.")
        return datos


class FormularioEstadoAlerta(MezclaEstilos, forms.Form):
    """Cambia el estado de una alerta."""

    estado = forms.ChoiceField(
        label="Nuevo estado",
        choices=[
            (EstadoAlerta.EN_PROCESO, "En proceso"),
            (EstadoAlerta.RESUELTA, "Resuelta"),
            (EstadoAlerta.IGNORADA, "Ignorada"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
