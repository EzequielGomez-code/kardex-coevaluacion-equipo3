"""
Formularios de Movimientos.

Cada operación (entrada, salida, transferencia, ajuste) separa la cabecera
de sus líneas: la cabecera es un formulario normal, las líneas son un
``formset`` — todas sus filas nacen «adicionales» (sin datos iniciales), así
que Django ya las trata como opcionales una por una: una fila que la persona
agrega y no llena, o que quita del DOM, simplemente no llega en el POST y no
genera un error de campo obligatorio.
"""

from __future__ import annotations

from django import forms

from apps.catalogo.models import Articulo, Cliente, Proveedor
from apps.nucleo.forms import MezclaEstilos
from apps.nucleo.models import Almacen

SIGNOS_AJUSTE = [(1, "Existencia encontrada (entra)"), (-1, "Existencia faltante (sale)")]


class FormularioTipoMovimiento(MezclaEstilos, forms.Form):
    """Alta y edición de un tipo de movimiento configurable."""

    codigo = forms.CharField(label="Código", max_length=20, help_text="Ejemplo: COMPRA, MERMA.")
    nombre = forms.CharField(label="Nombre", max_length=80)
    naturaleza = forms.ChoiceField(label="Naturaleza", choices=())
    prefijo_numeracion = forms.CharField(
        label="Prefijo de numeración", max_length=10, required=False,
        help_text="Vacío para usar el código. Ejemplo: ENT, SAL, TRF, AJU.",
    )
    exige_documento = forms.BooleanField(
        label="Exige número de documento", required=False,
    )
    exige_ncf = forms.BooleanField(label="Exige comprobante fiscal (NCF)", required=False)
    exige_motivo = forms.BooleanField(label="Exige motivo", required=False)
    exige_aprobacion = forms.BooleanField(label="Exige aprobación", required=False)
    permite_anulacion = forms.BooleanField(
        label="Permite anulación", required=False, initial=True,
    )
    tipo_contrapartida = forms.ModelChoiceField(
        label="Tipo de la contrapartida", queryset=None, required=False,
        empty_label="— El mismo tipo —",
        help_text="Con qué tipo se registra la anulación de este movimiento.",
    )
    color = forms.CharField(
        label="Color", max_length=7, required=False,
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    orden = forms.IntegerField(label="Orden", min_value=0, initial=10, required=False)
    activo = forms.BooleanField(label="Activo", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        from apps.movimientos.models import (  # pylint: disable=import-outside-toplevel
            Naturaleza,
            TipoMovimiento,
        )

        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        self.fields["naturaleza"].choices = Naturaleza.choices
        self.fields["tipo_contrapartida"].queryset = TipoMovimiento.objects.order_by("nombre")
        if es_edicion:
            self.fields["codigo"].disabled = True
            self.fields["naturaleza"].disabled = True
        self.aplicar_estilos()

    def clean_codigo(self) -> str:
        """Normaliza el código a mayúsculas."""
        return self.cleaned_data["codigo"].strip().upper()


class _FormularioCabecera(MezclaEstilos, forms.Form):
    """Campos comunes a toda cabecera de movimiento."""

    fecha = forms.DateTimeField(
        label="Fecha", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    motivo = forms.CharField(
        label="Motivo", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
    observaciones = forms.CharField(
        label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, tipos_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = tipos_queryset
        self.aplicar_estilos()


class FormularioEntradaCabecera(_FormularioCabecera):
    """Cabecera de una entrada: contra qué documento y de qué proveedor."""

    tipo = forms.ModelChoiceField(label="Tipo de movimiento", queryset=None)
    almacen_destino = forms.ModelChoiceField(
        label="Almacén de destino", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
    )
    proveedor = forms.ModelChoiceField(
        label="Proveedor", queryset=None, required=False, widget=forms.HiddenInput,
    )
    documento_tipo = forms.CharField(label="Tipo de documento", max_length=20, required=False)
    documento_numero = forms.CharField(label="Número de documento", max_length=40, required=False)
    ncf = forms.CharField(
        label="Comprobante fiscal (NCF)", max_length=19, required=False,
        help_text="Formato: letra + 10 dígitos. Ejemplo: B0100000001.",
    )
    fecha_documento = forms.DateField(
        label="Fecha del documento", required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        from apps.movimientos.models import (  # pylint: disable=import-outside-toplevel
            Naturaleza,
            TipoMovimiento,
        )

        super().__init__(
            *args,
            tipos_queryset=TipoMovimiento.objects.filter(
                naturaleza=Naturaleza.ENTRADA, activo=True
            ).order_by("orden"),
            **kwargs,
        )
        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True).order_by(
            "razon_social"
        )


class FormularioLineaEntrada(MezclaEstilos, forms.Form):
    """Una línea de entrada: qué artículo, cuánto y a qué costo."""

    articulo = forms.ModelChoiceField(
        label="Artículo", queryset=Articulo.objects.none(), required=False,
        widget=forms.HiddenInput,
    )
    cantidad = forms.DecimalField(
        label="Cantidad", max_digits=18, decimal_places=4, required=False, min_value=0.0001,
    )
    costo_unitario = forms.DecimalField(
        label="Costo unitario", max_digits=18, decimal_places=4, required=False, min_value=0,
    )
    numero_lote = forms.CharField(label="N.º de lote", max_length=30, required=False)
    fecha_vencimiento = forms.DateField(
        label="Vencimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["articulo"].queryset = Articulo.objects.filter(activo=True)
        self.aplicar_estilos()

    def clean(self) -> dict:
        """Una fila con artículo necesita cantidad y costo; una sin artículo se ignora."""
        datos = super().clean()
        if datos.get("articulo"):
            if not datos.get("cantidad"):
                self.add_error("cantidad", "Indique la cantidad.")
            if datos.get("costo_unitario") is None:
                self.add_error("costo_unitario", "Indique el costo unitario.")
        elif datos.get("cantidad") or datos.get("costo_unitario"):
            self.add_error("articulo", "Elija un artículo.")
        return datos


FormsetLineaEntrada = forms.formset_factory(FormularioLineaEntrada, extra=1)


class FormularioSalidaCabecera(_FormularioCabecera):
    """Cabecera de una salida: de qué almacén y para qué cliente."""

    tipo = forms.ModelChoiceField(label="Tipo de movimiento", queryset=None)
    almacen_origen = forms.ModelChoiceField(
        label="Almacén de origen", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
    )
    cliente = forms.ModelChoiceField(
        label="Cliente", queryset=None, required=False, widget=forms.HiddenInput,
    )
    documento_tipo = forms.CharField(label="Tipo de documento", max_length=20, required=False)
    documento_numero = forms.CharField(label="Número de documento", max_length=40, required=False)

    def __init__(self, *args, **kwargs):
        from apps.movimientos.models import (  # pylint: disable=import-outside-toplevel
            Naturaleza,
            TipoMovimiento,
        )

        super().__init__(
            *args,
            tipos_queryset=TipoMovimiento.objects.filter(
                naturaleza=Naturaleza.SALIDA, activo=True
            ).order_by("orden"),
            **kwargs,
        )
        self.fields["cliente"].queryset = Cliente.objects.filter(activo=True).order_by(
            "razon_social"
        )


class FormularioLineaSalida(MezclaEstilos, forms.Form):
    """Una línea de salida: qué artículo y cuánto — el costo lo resuelve el kardex."""

    articulo = forms.ModelChoiceField(
        label="Artículo", queryset=Articulo.objects.none(), required=False,
        widget=forms.HiddenInput,
    )
    cantidad = forms.DecimalField(
        label="Cantidad", max_digits=18, decimal_places=4, required=False, min_value=0.0001,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["articulo"].queryset = Articulo.objects.filter(activo=True)
        self.aplicar_estilos()

    def clean(self) -> dict:
        """Una fila con artículo necesita cantidad; una sin artículo se ignora."""
        datos = super().clean()
        if datos.get("articulo") and not datos.get("cantidad"):
            self.add_error("cantidad", "Indique la cantidad.")
        elif datos.get("cantidad") and not datos.get("articulo"):
            self.add_error("articulo", "Elija un artículo.")
        return datos


FormsetLineaSalida = forms.formset_factory(FormularioLineaSalida, extra=1)


class FormularioTransferenciaCabecera(_FormularioCabecera):
    """Cabecera de una transferencia entre dos almacenes."""

    tipo = forms.ModelChoiceField(label="Tipo de movimiento", queryset=None)
    almacen_origen = forms.ModelChoiceField(
        label="Almacén de origen", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
    )
    almacen_destino = forms.ModelChoiceField(
        label="Almacén de destino", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
    )

    def __init__(self, *args, **kwargs):
        from apps.movimientos.models import (  # pylint: disable=import-outside-toplevel
            Naturaleza,
            TipoMovimiento,
        )

        super().__init__(
            *args,
            tipos_queryset=TipoMovimiento.objects.filter(
                naturaleza=Naturaleza.TRANSFERENCIA, activo=True
            ).order_by("orden"),
            **kwargs,
        )

    def clean(self) -> dict:
        """Impide que origen y destino sean el mismo almacén."""
        datos = super().clean()
        origen = datos.get("almacen_origen")
        destino = datos.get("almacen_destino")
        if origen and destino and origen.pk == destino.pk:
            self.add_error("almacen_destino", "Debe ser distinto del almacén de origen.")
        return datos


FormsetLineaTransferencia = forms.formset_factory(FormularioLineaSalida, extra=1)


class FormularioAjusteCabecera(_FormularioCabecera):
    """Cabecera de un ajuste: siempre exige motivo."""

    tipo = forms.ModelChoiceField(label="Tipo de movimiento", queryset=None)
    almacen = forms.ModelChoiceField(
        label="Almacén", queryset=Almacen.objects.filter(activo=True).order_by("codigo"),
    )

    def __init__(self, *args, **kwargs):
        from apps.movimientos.models import (  # pylint: disable=import-outside-toplevel
            Naturaleza,
            TipoMovimiento,
        )

        super().__init__(
            *args,
            tipos_queryset=TipoMovimiento.objects.filter(
                naturaleza=Naturaleza.AJUSTE, activo=True
            ).order_by("orden"),
            **kwargs,
        )
        self.fields["motivo"].required = True

    def clean_motivo(self) -> str:
        """Todo ajuste necesita explicar por qué — sin excepción."""
        motivo = self.cleaned_data["motivo"].strip()
        if not motivo:
            raise forms.ValidationError("Todo ajuste necesita un motivo.")
        return motivo


class FormularioLineaAjuste(MezclaEstilos, forms.Form):
    """Una línea de ajuste: qué artículo, cuánto y en qué sentido."""

    articulo = forms.ModelChoiceField(
        label="Artículo", queryset=Articulo.objects.none(), required=False,
        widget=forms.HiddenInput,
    )
    cantidad = forms.DecimalField(
        label="Cantidad", max_digits=18, decimal_places=4, required=False, min_value=0.0001,
    )
    signo = forms.TypedChoiceField(
        label="Sentido", choices=SIGNOS_AJUSTE, coerce=int, required=False, initial=-1,
    )
    costo_unitario = forms.DecimalField(
        label="Costo unitario (si entra)", max_digits=18, decimal_places=4,
        required=False, min_value=0,
        help_text="Vacío para usar el costo promedio actual.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["articulo"].queryset = Articulo.objects.filter(activo=True)
        self.aplicar_estilos()

    def clean(self) -> dict:
        """Una fila con artículo necesita cantidad; una sin artículo se ignora."""
        datos = super().clean()
        if datos.get("articulo") and not datos.get("cantidad"):
            self.add_error("cantidad", "Indique la cantidad.")
        elif datos.get("cantidad") and not datos.get("articulo"):
            self.add_error("articulo", "Elija un artículo.")
        return datos


FormsetLineaAjuste = forms.formset_factory(FormularioLineaAjuste, extra=1)


class FormularioAnulacion(MezclaEstilos, forms.Form):
    """Motivo obligatorio para anular un movimiento."""

    motivo_anulacion = forms.CharField(
        label="Motivo de la anulación", widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class FormularioRechazo(MezclaEstilos, forms.Form):
    """Motivo obligatorio para rechazar un movimiento pendiente."""

    motivo = forms.CharField(label="Motivo del rechazo", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
