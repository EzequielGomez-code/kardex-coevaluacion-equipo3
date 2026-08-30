"""
Formularios de la app ``configuracion``.

``FormularioCamposDinamicos`` es el que pide el punto 4.2 del brief: arma sus
widgets en tiempo de ejecución a partir de las ``DefinicionCampo`` activas.
Las tres apps funcionales lo incrustan en sus propios formularios.
"""

from __future__ import annotations

from typing import Any

from django import forms

from apps.configuracion.models import DefinicionCampo, TipoDato
from apps.configuracion.services import ServicioCamposPersonalizados
from apps.nucleo.forms import MezclaEstilos
from apps.nucleo.models import Usuario


class FormularioCamposDinamicos(forms.Form):
    """
    Formulario que se construye solo a partir de las definiciones de campo.

    Uso típico dentro de otra vista::

        campos = FormularioCamposDinamicos(request.POST or None,
                                           entidad="Articulo",
                                           categoria=articulo.categoria,
                                           instancia=articulo)
        if formulario.is_valid() and campos.is_valid():
            articulo = formulario.save()
            campos.guardar(articulo)
    """

    def __init__(self, *args, entidad: str, categoria: str = "",
                 instancia: Any = None, **kwargs):
        self.entidad = entidad
        self.categoria = categoria
        self.instancia = instancia
        self.definiciones = ServicioCamposPersonalizados.campos_de(entidad, categoria)

        inicial = kwargs.pop("initial", None) or {}
        if instancia is not None and instancia.pk:
            guardados = ServicioCamposPersonalizados.valores_de(instancia, entidad)
            inicial = {**guardados, **inicial}
        kwargs["initial"] = inicial

        super().__init__(*args, **kwargs)

        for definicion in self.definiciones:
            self.fields[definicion.clave] = self._construir_campo(definicion)

    @staticmethod
    def _construir_campo(definicion: DefinicionCampo) -> forms.Field:
        """Devuelve el campo de formulario que corresponde al tipo declarado."""
        comunes: dict[str, Any] = {
            "label": definicion.etiqueta,
            "required": definicion.requerido,
            "help_text": definicion.ayuda,
        }
        opciones = [(str(opcion), str(opcion)) for opcion in definicion.opciones or []]

        if definicion.tipo == TipoDato.TEXTO:
            campo = forms.CharField(max_length=500, **comunes)
        elif definicion.tipo == TipoDato.NUMERO:
            campo = forms.IntegerField(**comunes)
        elif definicion.tipo == TipoDato.DECIMAL:
            campo = forms.DecimalField(max_digits=18, decimal_places=4, **comunes)
        elif definicion.tipo == TipoDato.FECHA:
            campo = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), **comunes)
        elif definicion.tipo == TipoDato.BOOLEANO:
            comunes["required"] = False
            campo = forms.BooleanField(**comunes)
        elif definicion.tipo == TipoDato.LISTA:
            campo = forms.ChoiceField(
                choices=[("", "— Seleccione —")] + opciones, **comunes
            )
        elif definicion.tipo == TipoDato.LISTA_MULTIPLE:
            campo = forms.MultipleChoiceField(
                choices=opciones, widget=forms.CheckboxSelectMultiple, **comunes
            )
        elif definicion.tipo == TipoDato.USUARIO:
            campo = forms.ModelChoiceField(
                queryset=Usuario.objects.filter(activo=True).order_by("nombre_completo"),
                empty_label="— Seleccione —",
                **comunes,
            )
        elif definicion.tipo == TipoDato.ARCHIVO:
            campo = forms.FileField(**comunes)
        else:
            campo = forms.CharField(max_length=500, **comunes)

        clase = "casilla" if definicion.tipo == TipoDato.BOOLEANO else "campo"
        existentes = campo.widget.attrs.get("class", "")
        campo.widget.attrs["class"] = f"{existentes} {clase}".strip()
        campo.widget.attrs["data-campo-personalizado"] = definicion.clave
        return campo

    def clean(self) -> dict:
        """
        Repite la validación en el servicio, que es la fuente de verdad.

        El formulario ya validó tipos básicos; el servicio comprueba además las
        opciones permitidas y los requeridos según la definición vigente
        (Seguridad #9).
        """
        datos = super().clean()
        try:
            ServicioCamposPersonalizados.validar(self.entidad, datos, self.categoria)
        except forms.ValidationError as error:
            for clave, mensajes in getattr(error, "message_dict", {}).items():
                for mensaje in mensajes:
                    self.add_error(clave if clave in self.fields else None, mensaje)
        return datos

    def guardar(self, objeto: Any) -> dict:
        """Persiste los valores del formulario contra el objeto indicado."""
        return ServicioCamposPersonalizados.guardar_valores(
            objeto, self.cleaned_data, entidad=self.entidad, categoria=self.categoria
        )


class FormularioDefinicionCampo(MezclaEstilos, forms.Form):
    """Alta y edición de una definición de campo desde la pantalla de administración."""

    entidad = forms.CharField(label="Entidad", max_length=60,
                              help_text="Modelo al que se cuelga: Articulo, Movimiento…")
    categoria = forms.CharField(
        label="Categoría",
        max_length=60,
        required=False,
        help_text="Vacío = aplica a todos los registros de la entidad.",
    )
    clave = forms.CharField(label="Clave", max_length=60,
                            help_text="Minúsculas y guion bajo. Ejemplo: peso_kg.")
    etiqueta = forms.CharField(label="Etiqueta visible", max_length=120)
    tipo = forms.ChoiceField(label="Tipo de dato", choices=TipoDato.choices)
    requerido = forms.BooleanField(label="Obligatorio", required=False)
    opciones = forms.CharField(
        label="Opciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Una opción por línea"}),
        help_text="Solo para los tipos de lista. Una opción por línea.",
    )
    ayuda = forms.CharField(label="Texto de ayuda", max_length=250, required=False)
    orden = forms.IntegerField(label="Orden", min_value=1, initial=100)
    activo = forms.BooleanField(label="Campo activo", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        if es_edicion:
            # Entidad y clave quedan fijas: los valores ya guardados dependen de ellas.
            self.fields["entidad"].disabled = True
            self.fields["categoria"].disabled = True
            self.fields["clave"].disabled = True
            self.fields["clave"].help_text = "La clave no se puede cambiar."
        self.aplicar_estilos()

    def clean_clave(self) -> str:
        """Normaliza la clave a minúsculas con guion bajo."""
        return self.cleaned_data["clave"].strip().lower().replace(" ", "_")

    def clean(self) -> dict:
        """Exige opciones cuando el tipo elegido es una lista."""
        datos = super().clean()
        tipo = datos.get("tipo")
        opciones = (datos.get("opciones") or "").strip()
        if tipo in {TipoDato.LISTA, TipoDato.LISTA_MULTIPLE} and not opciones:
            self.add_error("opciones", "Los campos de lista necesitan al menos una opción.")
        return datos


class FormularioParametros(forms.Form):
    """
    Formulario de «Parámetros del sistema».

    Se arma a partir de los parámetros existentes, agrupados por sección. Los
    parámetros marcados como no editables se muestran pero quedan bloqueados.
    """

    def __init__(self, *args, parametros: list | None = None, **kwargs):
        self.parametros = list(parametros or [])
        super().__init__(*args, **kwargs)

        for parametro in self.parametros:
            self.fields[parametro.clave] = self._construir_campo(parametro)

    @staticmethod
    def _construir_campo(parametro) -> forms.Field:
        """Devuelve el campo que corresponde al tipo del parámetro."""
        comunes: dict[str, Any] = {
            "label": parametro.etiqueta,
            "required": False,
            "help_text": parametro.ayuda,
            "initial": parametro.valor_convertido(),
        }

        if parametro.tipo == TipoDato.BOOLEANO:
            campo = forms.BooleanField(**comunes)
        elif parametro.tipo == TipoDato.NUMERO:
            campo = forms.IntegerField(**comunes)
        elif parametro.tipo == TipoDato.DECIMAL:
            campo = forms.DecimalField(max_digits=18, decimal_places=4, **comunes)
        elif parametro.tipo == TipoDato.LISTA and parametro.opciones:
            campo = forms.ChoiceField(
                choices=[(str(opcion), str(opcion)) for opcion in parametro.opciones], **comunes
            )
        else:
            campo = forms.CharField(max_length=500, **comunes)

        clase = "casilla" if parametro.tipo == TipoDato.BOOLEANO else "campo"
        campo.widget.attrs["class"] = clase
        if not parametro.editable:
            campo.disabled = True
            campo.help_text = "Este parámetro no se edita desde la interfaz."
        return campo

    def por_grupo(self) -> list[dict]:
        """Devuelve los campos agrupados por sección, para pintar la pantalla."""
        grupos: dict[str, list] = {}
        for parametro in self.parametros:
            grupos.setdefault(parametro.grupo, []).append(
                {"parametro": parametro, "campo": self[parametro.clave]}
            )
        return [{"nombre": nombre, "filas": filas} for nombre, filas in grupos.items()]
