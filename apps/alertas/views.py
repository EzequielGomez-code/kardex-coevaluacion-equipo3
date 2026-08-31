"""
Vistas de Alertas.

Cada vista comprueba su permiso en el servidor con ``@requiere_permiso``
(Seguridad #4) y delega en un servicio. Ninguna vista consulta el ORM
directamente.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.alertas.forms import FormularioEstadoAlerta, FormularioReglaAlerta
from apps.alertas.models import EstadoAlerta
from apps.alertas.services import ServicioAlertas, ServicioEvaluador, ServicioReglas
from apps.nucleo.decoradores import requiere_permiso
from apps.nucleo.repositories import RepositorioAlmacenes
from apps.nucleo.utilidades import entero_o_none, fichas_de_filtro, paginar, respuesta_exito

ETIQUETAS_ESTADO = {
    EstadoAlerta.ABIERTA: "Abierta", EstadoAlerta.EN_PROCESO: "En proceso",
    EstadoAlerta.RESUELTA: "Resuelta", EstadoAlerta.IGNORADA: "Ignorada",
}
VARIANTES_ESTADO = {
    EstadoAlerta.ABIERTA: "alerta", EstadoAlerta.EN_PROCESO: "aviso",
    EstadoAlerta.RESUELTA: "ok", EstadoAlerta.IGNORADA: "neutro",
}


def _volcar_errores(formulario, error: ValidationError) -> None:
    """Traslada los errores de un servicio a los campos de un formulario."""
    if hasattr(error, "error_dict"):
        for campo, errores in error.message_dict.items():
            destino = campo if campo in formulario.fields else None
            for mensaje in errores:
                formulario.add_error(destino, mensaje)
    else:
        for mensaje in error.messages:
            formulario.add_error(None, mensaje)


@requiere_permiso("alerta.ver")
def indice(request: HttpRequest) -> HttpResponse:
    """Bandeja de alertas, con filtros por estado y almacén."""
    busqueda = request.GET.get("busqueda", "").strip()
    estado = request.GET.get("estado", "").strip()
    almacen_id = entero_o_none(request.GET.get("almacen"))

    consulta = ServicioAlertas.listar(busqueda=busqueda, estado=estado, almacen_id=almacen_id)
    contexto = {
        "titulo": "Alertas",
        "migas": [{"texto": "Inventario"}, {"texto": "Alertas"}],
        "busqueda": busqueda, "estado": estado, "almacen_id": almacen_id,
        "almacenes": RepositorioAlmacenes.activos(),
        "estados": EstadoAlerta.choices,
        "etiquetas_estado": ETIQUETAS_ESTADO, "variantes_estado": VARIANTES_ESTADO,
        "columnas_alerta": [
            {"etiqueta": "Artículo"}, {"etiqueta": "Almacén"}, {"etiqueta": "Mensaje"},
            {"etiqueta": "Generada"}, {"etiqueta": "Estado"},
        ],
        "fichas_filtro": fichas_de_filtro(
            request, {"busqueda": "Busca", "estado": "Estado", "almacen": "Almacén"},
            {"estado": ETIQUETAS_ESTADO},
        ),
        **paginar(request, consulta),
    }
    return render(request, "alertas/indice.html", contexto)


@requiere_permiso("alerta.resolver")
@require_http_methods(["POST"])
def evaluar_ahora(request: HttpRequest) -> HttpResponse:
    """Vuelve a evaluar todas las reglas activas contra el inventario actual."""
    evaluadas = ServicioEvaluador.evaluar_todo()
    return respuesta_exito(f"Evaluación completa: {evaluadas} reglas revisadas.")


@requiere_permiso("alerta.resolver")
@require_http_methods(["GET", "POST"])
def alerta_cambiar_estado(request: HttpRequest, alerta_id: int) -> HttpResponse:
    """Cambia el estado de una alerta (en proceso, resuelta, ignorada)."""
    alerta = ServicioAlertas.obtener(alerta_id)
    if alerta is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioEstadoAlerta(request.POST)
        if formulario.is_valid():
            try:
                ServicioAlertas.cambiar_estado(
                    alerta, formulario.cleaned_data["estado"], request.user
                )
                return respuesta_exito(f"Alerta de «{alerta.articulo.sku}» actualizada.")
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        formulario = FormularioEstadoAlerta(initial={"estado": EstadoAlerta.EN_PROCESO})

    contexto = {
        "formulario": formulario, "alerta": alerta,
        "titulo_modal": "Actualizar alerta",
        "destino": reverse("alertas:alerta_estado", args=[alerta.pk]),
        "etiqueta_envio": "Guardar",
    }
    return render(request, "alertas/alerta_estado.html", contexto)


@requiere_permiso("alerta.configurar")
def reglas(request: HttpRequest) -> HttpResponse:
    """Listado de reglas de alerta configuradas."""
    contexto = {
        "titulo": "Reglas de alerta",
        "migas": [{"texto": "Inventario"}, {"texto": "Alertas", "destino": reverse("alertas:indice")},
                 {"texto": "Reglas"}],
        "reglas": ServicioReglas.listar(),
        "columnas_regla": [
            {"etiqueta": "Nombre"}, {"etiqueta": "Tipo"}, {"etiqueta": "Días"},
            {"etiqueta": "Alcance"}, {"etiqueta": "Estado"},
        ],
    }
    return render(request, "alertas/reglas.html", contexto)


@requiere_permiso("alerta.configurar")
@require_http_methods(["GET", "POST"])
def regla_formulario(request: HttpRequest, regla_id: int | None = None) -> HttpResponse:
    """Alta o edición de una regla de alerta."""
    regla = ServicioReglas.obtener(regla_id) if regla_id else None
    if regla_id and regla is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioReglaAlerta(request.POST)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                if regla:
                    datos.pop("tipo", None)
                    guardada = ServicioReglas.actualizar(regla, **datos)
                    mensaje = f"Regla «{guardada.nombre}» actualizada."
                else:
                    guardada = ServicioReglas.crear(**datos)
                    mensaje = f"Regla «{guardada.nombre}» creada."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                _volcar_errores(formulario, error)
    else:
        inicial = {}
        if regla:
            inicial = {
                "nombre": regla.nombre, "tipo": regla.tipo, "dias_umbral": regla.dias_umbral,
                "almacenes": list(regla.almacenes.values_list("pk", flat=True)),
                "categorias": list(regla.categorias.values_list("pk", flat=True)),
                "activa": regla.activa,
            }
        formulario = FormularioReglaAlerta(initial=inicial)
        if regla:
            formulario.fields["tipo"].disabled = True

    contexto = {
        "formulario": formulario, "titulo_modal": "Editar regla" if regla else "Nueva regla",
        "destino": (
            reverse("alertas:regla_editar", args=[regla.pk]) if regla
            else reverse("alertas:regla_nueva")
        ),
        "etiqueta_envio": "Guardar cambios" if regla else "Crear regla",
    }
    return render(request, "alertas/regla_formulario.html", contexto)
