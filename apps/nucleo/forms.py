"""
Formularios del núcleo.

Se escriben a mano en lugar de usar ``django-crispy-forms``: el brief lo
permite (punto 2) y el sistema de diseño propio necesita control exacto del
marcado. Toda validación que aquí aparece se repite del lado del servidor en
los servicios, porque la del cliente es solo comodidad (Seguridad #9).
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from apps.nucleo.models import Almacen, Permiso, Rol, Usuario


class MezclaEstilos:
    """Aplica las clases del sistema de diseño a todos los widgets del formulario."""

    CLASES_POR_WIDGET = {
        forms.CheckboxInput: "casilla",
        forms.Select: "campo campo--seleccion",
        forms.SelectMultiple: "campo campo--seleccion",
        forms.Textarea: "campo campo--area",
    }

    def aplicar_estilos(self) -> None:
        """Añade la clase CSS que corresponde a cada widget."""
        for campo in self.fields.values():  # type: ignore[attr-defined]
            clase = self.CLASES_POR_WIDGET.get(type(campo.widget), "campo")
            existentes = campo.widget.attrs.get("class", "")
            campo.widget.attrs["class"] = f"{existentes} {clase}".strip()
            if campo.required:
                campo.widget.attrs["required"] = "required"


class FormularioInicioSesion(AuthenticationForm):
    """Formulario de acceso. Los mensajes van en español y sin revelar detalles."""

    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "Esta cuenta está desactivada.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["username"].widget.attrs.update(
            {"class": "campo", "autofocus": True, "autocomplete": "username",
             "placeholder": "nombre de acceso"}
        )
        self.fields["password"].label = "Contraseña"
        self.fields["password"].widget.attrs.update(
            {"class": "campo", "autocomplete": "current-password", "placeholder": "••••••••"}
        )


class FormularioRol(MezclaEstilos, forms.Form):
    """Alta y edición de un rol con su juego de permisos."""

    nombre = forms.CharField(label="Nombre del rol", max_length=60)
    descripcion = forms.CharField(
        label="Descripción",
        max_length=200,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    permisos = forms.MultipleChoiceField(
        label="Permisos",
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Las claves se leen de la base para que un permiso nuevo aparezca solo.
        self.fields["permisos"].choices = [
            (permiso.clave, permiso.descripcion)
            for permiso in Permiso.objects.all().order_by("modulo", "clave")
        ]
        self.aplicar_estilos()

    def clean_nombre(self) -> str:
        """Normaliza el nombre y exige al menos tres caracteres."""
        nombre = self.cleaned_data["nombre"].strip()
        if len(nombre) < 3:
            raise forms.ValidationError("El nombre debe tener al menos 3 caracteres.")
        return nombre


class FormularioUsuario(MezclaEstilos, forms.Form):
    """
    Alta y edición de usuarios.

    En la edición el nombre de acceso queda fijo y la contraseña es opcional:
    si se deja en blanco, se conserva la que ya tenía.
    """

    username = forms.CharField(label="Nombre de acceso", max_length=150)
    nombre_completo = forms.CharField(label="Nombre completo", max_length=150)
    email = forms.EmailField(label="Correo electrónico", required=False)
    telefono = forms.CharField(label="Teléfono", max_length=30, required=False)
    rol = forms.ModelChoiceField(
        label="Rol",
        queryset=Rol.objects.all().order_by("nombre"),
        required=False,
        empty_label="— Sin rol asignado —",
    )
    contrasena = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Mínimo 10 caracteres.",
    )
    confirmacion = forms.CharField(
        label="Repetir contraseña",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
    )
    activo = forms.BooleanField(label="Usuario activo", required=False, initial=True)

    def __init__(self, *args, es_edicion: bool = False, **kwargs):
        self.es_edicion = es_edicion
        super().__init__(*args, **kwargs)
        if es_edicion:
            self.fields["username"].disabled = True
            self.fields["username"].help_text = "El nombre de acceso no se puede cambiar."
            self.fields["contrasena"].help_text = "Déjela en blanco para no cambiarla."
        else:
            self.fields["contrasena"].required = True
            self.fields["confirmacion"].required = True
        self.aplicar_estilos()

    def clean_username(self) -> str:
        """Normaliza el nombre de acceso a minúsculas sin espacios."""
        return self.cleaned_data["username"].strip().lower()

    def clean(self) -> dict:
        """Comprueba que las dos contraseñas coincidan y tengan largo suficiente."""
        datos = super().clean()
        contrasena = datos.get("contrasena") or ""
        confirmacion = datos.get("confirmacion") or ""

        if contrasena or confirmacion:
            if contrasena != confirmacion:
                self.add_error("confirmacion", "Las contraseñas no coinciden.")
            elif len(contrasena) < 10:
                self.add_error("contrasena", "La contraseña debe tener al menos 10 caracteres.")
        return datos


class FormularioAlmacen(MezclaEstilos, forms.ModelForm):
    """Alta y edición de almacenes."""

    class Meta:
        model = Almacen
        fields = ["codigo", "nombre", "direccion", "encargado", "activo"]
        labels = {
            "codigo": "Código",
            "nombre": "Nombre",
            "direccion": "Dirección",
            "encargado": "Encargado",
            "activo": "Almacén activo",
        }
        widgets = {
            "direccion": forms.Textarea(attrs={"rows": 2}),
            "codigo": forms.TextInput(attrs={"placeholder": "ALM-01", "class": "campo mono"}),
        }
        help_texts = {
            "codigo": "Mayúsculas, números y guiones. Ejemplo: ALM-01.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["encargado"].queryset = Usuario.objects.filter(activo=True).order_by(
            "nombre_completo"
        )
        self.fields["encargado"].empty_label = "— Sin encargado —"
        self.fields["direccion"].required = False
        self.aplicar_estilos()

    def clean_codigo(self) -> str:
        """Normaliza el código a mayúsculas."""
        return self.cleaned_data["codigo"].strip().upper()
