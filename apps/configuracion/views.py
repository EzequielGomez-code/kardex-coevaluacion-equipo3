"""
Vistas de configuración: parámetros del sistema, campos personalizados y
etiquetas.

Todas exigen el permiso ``configuracion.gestionar`` en el servidor
(Seguridad #4). Ninguna consulta el ORM directamente: pasan por los servicios.
"""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.configuracion.forms import FormularioDefinicionCampo, FormularioParametros
from apps.configuracion.models import Etiqueta, TipoDato
from apps.configuracion.repositories import RepositorioEtiquetas
from apps.configuracion.services import ServicioDefinicionesCampo, ServicioParametros
from apps.nucleo.decoradores import requiere_permiso
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria
from apps.nucleo.utilidades import ordenar, paginar, respuesta_aviso, respuesta_exito

# Columnas de la tabla de etiquetas (ver nota en apps/nucleo/views.py).
COLUMNAS_ETIQUETA = [
    {"etiqueta": "Etiqueta", "clave": "nombre"},
    {"etiqueta": "Color"},
    {"etiqueta": "Asignaciones", "clase": "num"},
    {"etiqueta": "Estado"},
]
PERMITIDAS_ETIQUETA = {"nombre": "nombre"}


# ---------------------------------------------------------------------------
# Parámetros del sistema
# ---------------------------------------------------------------------------
@requiere_permiso("configuracion.gestionar")
@require_http_methods(["GET", "POST"])
def parametros(request: HttpRequest) -> HttpResponse:
    """
    Pantalla de parámetros, agrupada por secciones.

    Al guardar, el cambio se refleja en el acto porque los parámetros se leen
    de la base en cada petición (criterio 9.6 del brief).
    """
    listado = list(ServicioParametros.listar())

    if request.method == "POST":
        formulario = FormularioParametros(request.POST, parametros=listado)
        if formulario.is_valid():
            enviados = {
                parametro.clave: formulario.cleaned_data.get(parametro.clave)
                for parametro in listado
                if parametro.editable
            }
            try:
                cantidad = ServicioParametros.guardar_muchos(enviados)
            except ValidationError as error:
                for clave, mensajes in error.message_dict.items():
                    for mensaje in mensajes:
                        formulario.add_error(
                            clave if clave in formulario.fields else None, mensaje
                        )
            else:
                if cantidad:
                    texto = (
                        "1 parámetro actualizado."
                        if cantidad == 1
                        else f"{cantidad} parámetros actualizados."
                    )
                else:
                    texto = "No hubo cambios que guardar."
                return respuesta_exito(texto, recargar=True)
    else:
        formulario = FormularioParametros(parametros=listado)

    contexto = {
        "titulo": "Parámetros del sistema",
        "migas": [{"texto": "Sistema"}, {"texto": "Parámetros"}],
        "formulario": formulario,
        "grupos": formulario.por_grupo(),
    }
    return render(request, "configuracion/parametros.html", contexto)


# ---------------------------------------------------------------------------
# Campos personalizados
# ---------------------------------------------------------------------------
@requiere_permiso("configuracion.gestionar")
def campos(request: HttpRequest) -> HttpResponse:
    """Listado de definiciones de campo, agrupadas por entidad y reordenables."""
    entidad = request.GET.get("entidad", "")
    consulta = ServicioDefinicionesCampo.listar(entidad=entidad)

    contexto = {
        "titulo": "Campos personalizados",
        "migas": [{"texto": "Sistema"}, {"texto": "Campos personalizados"}],
        "entidad": entidad,
        "entidades": ServicioDefinicionesCampo.entidades(),
        "tipos": dict(TipoDato.choices),
        **paginar(request, consulta, por_pagina=50),
    }
    return render(request, "configuracion/campos.html", contexto)


@requiere_permiso("configuracion.gestionar")
@require_http_methods(["GET", "POST"])
def campo_formulario(request: HttpRequest, definicion_id: int | None = None) -> HttpResponse:
    """Alta o edición de una definición de campo, dentro de un modal HTMX."""
    definicion = ServicioDefinicionesCampo.obtener(definicion_id) if definicion_id else None
    if definicion_id and definicion is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioDefinicionCampo(request.POST, es_edicion=definicion is not None)
        if formulario.is_valid():
            datos = dict(formulario.cleaned_data)
            try:
                if definicion:
                    ServicioDefinicionesCampo.actualizar(definicion, **datos)
                    mensaje = f"Campo «{datos['etiqueta']}» actualizado."
                else:
                    ServicioDefinicionesCampo.crear(**datos)
                    mensaje = f"Campo «{datos['etiqueta']}» creado."
                return respuesta_exito(mensaje)
            except ValidationError as error:
                for clave, mensajes in getattr(error, "message_dict", {}).items():
                    for texto in mensajes:
                        formulario.add_error(
                            clave if clave in formulario.fields else None, texto
                        )
    else:
        inicial = {"entidad": request.GET.get("entidad", "")}
        if definicion:
            inicial = {
                "entidad": definicion.entidad,
                "categoria": definicion.categoria,
                "clave": definicion.clave,
                "etiqueta": definicion.etiqueta,
                "tipo": definicion.tipo,
                "requerido": definicion.requerido,
                "opciones": "\n".join(str(opcion) for opcion in definicion.opciones or []),
                "ayuda": definicion.ayuda,
                "orden": definicion.orden,
                "activo": definicion.activo,
            }
        formulario = FormularioDefinicionCampo(
            initial=inicial, es_edicion=definicion is not None
        )

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar campo" if definicion else "Nuevo campo personalizado",
        "destino": (
            reverse("configuracion:campo_editar", args=[definicion.pk])
            if definicion
            else reverse("configuracion:campo_nuevo")
        ),
        "etiqueta_envio": "Guardar cambios" if definicion else "Crear campo",
        "tipos_con_opciones": [TipoDato.LISTA.value, TipoDato.LISTA_MULTIPLE.value],
    }
    return render(request, "configuracion/campo_formulario.html", contexto)


@requiere_permiso("configuracion.gestionar")
@require_http_methods(["POST"])
def campos_reordenar(request: HttpRequest) -> HttpResponse:
    """
    Recibe el nuevo orden de los campos tras arrastrarlos en pantalla.

    El cuerpo llega como JSON: ``{"orden": [12, 7, 30]}``.
    """
    try:
        cuerpo = json.loads(request.body.decode("utf-8") or "{}")
        identificadores = [int(valor) for valor in cuerpo.get("orden", [])]
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Orden inválido."}, status=400)

    if not identificadores:
        return JsonResponse({"error": "No se recibió ningún campo."}, status=400)

    ServicioDefinicionesCampo.reordenar(identificadores)
    return JsonResponse({"guardado": True, "total": len(identificadores)})


# ---------------------------------------------------------------------------
# Etiquetas
# ---------------------------------------------------------------------------
@requiere_permiso("configuracion.gestionar")
def etiquetas(request: HttpRequest) -> HttpResponse:
    """Listado de etiquetas de color."""
    consulta = ordenar(RepositorioEtiquetas.listar(), request, PERMITIDAS_ETIQUETA)
    contexto = {
        "titulo": "Etiquetas",
        "migas": [{"texto": "Sistema"}, {"texto": "Etiquetas"}],
        "columnas_etiqueta": COLUMNAS_ETIQUETA,
        **paginar(request, consulta),
    }
    return render(request, "configuracion/etiquetas.html", contexto)


@requiere_permiso("configuracion.gestionar")
@require_http_methods(["GET", "POST"])
def etiqueta_formulario(request: HttpRequest, etiqueta_id: int | None = None) -> HttpResponse:
    """Alta o edición de una etiqueta dentro de un modal HTMX."""
    from django import forms  # pylint: disable=import-outside-toplevel

    class FormularioEtiqueta(forms.ModelForm):
        """Formulario mínimo de etiqueta; vive aquí por ser de una sola pantalla."""

        class Meta:
            """Campos y etiquetas del formulario."""

            model = Etiqueta
            fields = ["nombre", "color", "activo"]
            labels = {"nombre": "Nombre", "color": "Color", "activo": "Etiqueta activa"}
            widgets = {"color": forms.TextInput(attrs={"type": "color", "class": "campo-color"})}

    etiqueta = Etiqueta.objects.filter(pk=etiqueta_id).first() if etiqueta_id else None
    if etiqueta_id and etiqueta is None:
        return render(request, "componentes/no_encontrado.html", status=404)

    if request.method == "POST":
        formulario = FormularioEtiqueta(request.POST, instance=etiqueta)
        if formulario.is_valid():
            guardada = formulario.save()
            ServicioAuditoria.registrar(
                entidad="Etiqueta",
                entidad_id=guardada.pk,
                accion=(
                    RegistroAuditoria.Accion.EDITAR
                    if etiqueta
                    else RegistroAuditoria.Accion.CREAR
                ),
                detalle={"nombre": guardada.nombre, "color": guardada.color},
            )
            return respuesta_exito(f"Etiqueta «{guardada.nombre}» guardada.")
    else:
        formulario = FormularioEtiqueta(instance=etiqueta)

    for nombre, campo in formulario.fields.items():
        if nombre != "color":
            clase = "casilla" if nombre == "activo" else "campo"
            campo.widget.attrs["class"] = clase

    contexto = {
        "formulario": formulario,
        "titulo_modal": "Editar etiqueta" if etiqueta else "Nueva etiqueta",
        "destino": (
            reverse("configuracion:etiqueta_editar", args=[etiqueta.pk])
            if etiqueta
            else reverse("configuracion:etiqueta_nueva")
        ),
        "etiqueta_envio": "Guardar",
    }
    return render(request, "configuracion/etiqueta_formulario.html", contexto)


@requiere_permiso("configuracion.gestionar")
@require_http_methods(["POST"])
def etiqueta_alternar(request: HttpRequest, etiqueta_id: int) -> HttpResponse:
    """Activa o desactiva una etiqueta sin abrir el modal."""
    etiqueta = Etiqueta.objects.filter(pk=etiqueta_id).first()
    if etiqueta is None:
        return respuesta_aviso("La etiqueta ya no existe.")
    etiqueta.activo = not etiqueta.activo
    etiqueta.save(update_fields=["activo", "actualizado_en"])
    ServicioAuditoria.registrar(
        entidad="Etiqueta",
        entidad_id=etiqueta.pk,
        accion=RegistroAuditoria.Accion.EDITAR,
        detalle={"activo": etiqueta.activo},
    )
    estado = "activada" if etiqueta.activo else "desactivada"
    return respuesta_exito(f"Etiqueta «{etiqueta.nombre}» {estado}.")
