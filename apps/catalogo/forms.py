"""
Formularios del catálogo.

Se escriben a mano, como el resto del sistema (punto 2 del brief): el diseño
propio necesita control exacto del marcado.
"""

from __future__ import annotations

from django import forms

from apps.catalogo.models import Marca, UnidadMedida
from apps.nucleo.forms import MezclaEstilos

ICONOS_CATEGORIA = [
    ("catalogo", "Genérico"),
    ("almacen", "Almacén"),
    ("camion", "Herramientas / equipo"),
    ("candado", "Ferretería / seguridad"),
    ("grafico", "Materiales"),
]


class FormularioCategoria(MezclaEstilos, forms.Form):
    """Alta y edición de una categoría. El padre se resuelve en la vista, no aquí."""

    codigo = forms.CharField(
        label="Código", max_length=30,
        help_text="Mayúsculas, números, guiones. Ejemplo: CEM-SACOS.",
    )
    nombre = forms.CharField(label="Nombre", max_length=120)
    descripcion = forms.CharField(
        label="Descripción", max_length=250, required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    icono = forms.ChoiceField(label="Ícono", choices=ICONOS_CATEGORIA, initial="catalogo")
    activo = forms.BooleanField(label="Categoría activa", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        if es_edicion:
            self.fields["codigo"].disabled = True
            self.fields["codigo"].help_text = "El código no se puede cambiar."
        self.aplicar_estilos()

    def clean_codigo(self) -> str:
        """Normaliza el código a mayúsculas."""
        return self.cleaned_data["codigo"].strip().upper()


class FormularioMarca(MezclaEstilos, forms.Form):
    """Alta y edición de una marca."""

    nombre = forms.CharField(label="Nombre", max_length=120)
    pais = forms.CharField(label="País de origen", max_length=60, required=False)
    sitio_web = forms.URLField(label="Sitio web", required=False)
    activo = forms.BooleanField(label="Marca activa", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()


class FormularioUnidadMedida(MezclaEstilos, forms.Form):
    """Alta y edición de una unidad de medida."""

    codigo = forms.CharField(
        label="Código", max_length=10, help_text="Ejemplo: UD, SC, QQ, M, KG, GL.",
    )
    nombre = forms.CharField(label="Nombre", max_length=60)
    simbolo = forms.CharField(label="Símbolo", max_length=10, required=False)
    permite_decimales = forms.BooleanField(
        label="Permite cantidades con decimales", required=False, initial=True,
    )
    activo = forms.BooleanField(label="Unidad activa", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        if es_edicion:
            self.fields["codigo"].disabled = True
        self.aplicar_estilos()


class FormularioArticulo(MezclaEstilos, forms.Form):
    """
    Alta y edición de un artículo.

    El SKU es opcional al crear: si se deja en blanco, el servicio lo genera
    con el formato configurable ``formato_sku``.
    """

    sku = forms.CharField(
        label="SKU", max_length=40, required=False,
        help_text="Vacío para generarlo solo, según el formato configurado.",
    )
    codigo_barras = forms.CharField(label="Código de barras", max_length=20, required=False)
    nombre = forms.CharField(label="Nombre", max_length=200)
    descripcion = forms.CharField(
        label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 3}),
    )
    categoria = forms.ModelChoiceField(
        label="Categoría", queryset=None, empty_label="— Seleccione —",
    )
    marca = forms.ModelChoiceField(
        label="Marca", queryset=None, required=False, empty_label="— Sin marca —",
    )
    unidad = forms.ModelChoiceField(label="Unidad de medida", queryset=None)
    es_inventariable = forms.BooleanField(
        label="Controla existencia", required=False, initial=True,
    )
    maneja_lotes = forms.BooleanField(label="Maneja lotes", required=False, initial=True)
    maneja_vencimiento = forms.BooleanField(
        label="Maneja fecha de vencimiento", required=False,
    )
    costo_referencia = forms.DecimalField(
        label="Costo de referencia", max_digits=18, decimal_places=4, required=False, min_value=0,
    )
    precio_venta = forms.DecimalField(
        label="Precio de venta", max_digits=18, decimal_places=4, required=False, min_value=0,
    )
    tasa_itbis = forms.DecimalField(
        label="Tasa de ITBIS (%)", max_digits=5, decimal_places=2, initial=18, min_value=0,
    )
    stock_minimo_defecto = forms.DecimalField(
        label="Existencia mínima por defecto", max_digits=18, decimal_places=4,
        required=False, min_value=0,
    )
    imagen = forms.ImageField(label="Imagen", required=False)
    activo = forms.BooleanField(label="Artículo activo", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        # Importación diferida: evita un ciclo entre catalogo y sus propios
        # modelos al cargar el módulo de formularios antes que el de modelos.
        from apps.catalogo.models import Categoria  # pylint: disable=import-outside-toplevel

        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.filter(activo=True).order_by("ruta")
        self.fields["marca"].queryset = Marca.objects.filter(activo=True).order_by("nombre")
        self.fields["unidad"].queryset = UnidadMedida.objects.filter(activo=True).order_by("codigo")
        self.aplicar_estilos()
        self.fields["categoria"].widget.attrs["data-recargar-campos"] = "true"


class _FormularioTercero(MezclaEstilos, forms.Form):
    """Base compartida por el formulario de proveedor y el de cliente."""

    codigo = forms.CharField(label="Código", max_length=20)
    razon_social = forms.CharField(label="Razón social", max_length=200)
    nombre_comercial = forms.CharField(label="Nombre comercial", max_length=200, required=False)
    tipo_documento = forms.ChoiceField(
        label="Tipo de documento",
        choices=[("rnc", "RNC"), ("cedula", "Cédula"), ("pasaporte", "Pasaporte")],
        initial="rnc",
    )
    rnc = forms.CharField(label="RNC o cédula", max_length=13, required=False)
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)
    email = forms.EmailField(label="Correo electrónico", required=False)
    direccion = forms.CharField(
        label="Dirección", max_length=250, required=False, widget=forms.Textarea(attrs={"rows": 2}),
    )
    contacto = forms.CharField(label="Persona de contacto", max_length=120, required=False)
    dias_credito = forms.IntegerField(label="Días de crédito", min_value=0, required=False)
    limite_credito = forms.DecimalField(
        label="Límite de crédito", max_digits=18, decimal_places=2, min_value=0, required=False,
    )
    notas = forms.CharField(label="Notas", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    activo = forms.BooleanField(label="Activo", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        if es_edicion:
            self.fields["codigo"].disabled = True
        self.aplicar_estilos()

    def clean_codigo(self) -> str:
        """Normaliza el código a mayúsculas."""
        return self.cleaned_data["codigo"].strip().upper()


class FormularioProveedor(_FormularioTercero):
    """Alta y edición de un proveedor."""


class FormularioCliente(_FormularioTercero):
    """Alta y edición de un cliente."""


class FormularioImportacionArticulos(MezclaEstilos, forms.Form):
    """
    Mapeo de columnas para la carga masiva de artículos.

    Cada campo es el nombre exacto de la columna en el archivo del usuario —
    no una lista desplegable de encabezados detectados, para no necesitar un
    primer viaje al servidor solo para leer la fila 1.
    """

    archivo = forms.FileField(label="Archivo CSV")

    def __init__(self, *args, **kwargs):
        from apps.catalogo.importacion import COLUMNAS_SISTEMA  # pylint: disable=import-outside-toplevel

        super().__init__(*args, **kwargs)
        for campo, etiqueta, obligatoria in COLUMNAS_SISTEMA:
            self.fields[campo] = forms.CharField(
                label=f"Columna para «{etiqueta}»", required=obligatoria,
            )
        # El archivo va al final del marcado a propósito: el mapeo se lee de
        # arriba hacia abajo antes de pedir el archivo.
        self.order_fields([campo for campo, *_ in COLUMNAS_SISTEMA] + ["archivo"])
        self.aplicar_estilos()

    def mapeo(self) -> dict:
        """Traduce los datos limpios del formulario a ``{campo: encabezado}``."""
        from apps.catalogo.importacion import COLUMNAS_SISTEMA  # pylint: disable=import-outside-toplevel

        return {campo: self.cleaned_data.get(campo, "") for campo, *_ in COLUMNAS_SISTEMA}


class FormularioPrecioProveedor(MezclaEstilos, forms.Form):
    """Precio de compra de un proveedor para un artículo."""

    codigo_proveedor = forms.CharField(
        label="Código del proveedor para este artículo", max_length=40, required=False,
    )
    precio_compra = forms.DecimalField(
        label="Precio de compra", max_digits=18, decimal_places=4, min_value=0,
    )
    tiempo_entrega_dias = forms.IntegerField(
        label="Tiempo de entrega (días)", min_value=0, required=False, initial=0,
    )
    cantidad_minima = forms.DecimalField(
        label="Cantidad mínima de pedido", max_digits=18, decimal_places=4,
        min_value=0, required=False, initial=1,
    )
    es_preferido = forms.BooleanField(label="Proveedor preferido", required=False)
    activo = forms.BooleanField(label="Relación activa", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos()
