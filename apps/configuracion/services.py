"""
Servicios de configuración.

``ServicioCamposPersonalizados`` es la puerta que usan las tres apps
funcionales para colgar campos propios de cualquier modelo sin tocar esta app.
``ServicioParametros`` resuelve los valores globales editables desde pantalla.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.configuracion.models import DefinicionCampo, Parametro, TipoDato
from apps.configuracion.repositories import (
    RepositorioDefinicionesCampo,
    RepositorioParametros,
    RepositorioValoresCampo,
)
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria


class ServicioParametros:
    """
    Lee y escribe los parámetros globales del sistema.

    No se guarda caché entre peticiones a propósito: así, al editar un
    parámetro, el cambio se refleja de inmediato y sin reiniciar el servidor
    (criterio 9.6 del brief). Son unas pocas decenas de filas y se leen una
    sola vez por petición desde el procesador de contexto.
    """

    @staticmethod
    def todos() -> dict[str, Any]:
        """Devuelve un diccionario ``clave -> valor convertido``."""
        return {
            parametro.clave: parametro.valor_convertido()
            for parametro in RepositorioParametros.todos()
        }

    @staticmethod
    def obtener(clave: str, por_defecto: Any = None) -> Any:
        """Devuelve el valor de un parámetro ya convertido a su tipo."""
        parametro = RepositorioParametros.obtener(clave)
        return parametro.valor_convertido() if parametro else por_defecto

    @staticmethod
    def listar(grupo: str = "", busqueda: str = "") -> Any:
        """Devuelve los parámetros filtrados, para la pantalla de configuración."""
        return RepositorioParametros.listar(grupo=grupo, busqueda=busqueda)

    @staticmethod
    def grupos() -> list[str]:
        """Devuelve los grupos de parámetros existentes."""
        return RepositorioParametros.grupos()

    @staticmethod
    @transaction.atomic
    def guardar_muchos(valores: dict[str, str]) -> int:
        """
        Guarda varios parámetros de una vez y deja constancia de los cambios.

        :param valores: diccionario ``clave -> valor en texto`` tal como llega
            del formulario.
        :returns: cantidad de parámetros que efectivamente cambiaron.
        :raises ValidationError: si algún valor no corresponde a su tipo.
        """
        cambios: dict[str, dict[str, Any]] = {}

        for clave, valor_nuevo in valores.items():
            parametro = RepositorioParametros.obtener(clave)
            if parametro is None or not parametro.editable:
                continue

            texto = ServicioParametros._normalizar(parametro, valor_nuevo)
            if texto == parametro.valor:
                continue

            cambios[clave] = {"antes": parametro.valor, "despues": texto}
            parametro.valor = texto
            parametro.save(update_fields=["valor", "actualizado_en"])

        if cambios:
            ServicioAuditoria.registrar(
                entidad="Parametro",
                accion=RegistroAuditoria.Accion.EDITAR,
                detalle=cambios,
            )
        return len(cambios)

    @staticmethod
    def _normalizar(parametro: Parametro, valor: Any) -> str:
        """
        Convierte el valor recibido del formulario al texto que se guarda.

        :raises ValidationError: si el valor no encaja con el tipo declarado.
        """
        if parametro.tipo == TipoDato.BOOLEANO:
            encendido = str(valor).strip().lower() in {"1", "true", "on", "si", "sí"}
            return "true" if encendido else "false"

        texto = "" if valor is None else str(valor).strip()

        if parametro.tipo == TipoDato.NUMERO:
            try:
                return str(int(texto))
            except (TypeError, ValueError) as error:
                raise ValidationError(
                    {parametro.clave: f"«{parametro.etiqueta}» debe ser un número entero."}
                ) from error

        if parametro.tipo == TipoDato.DECIMAL:
            try:
                return str(Decimal(texto))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise ValidationError(
                    {parametro.clave: f"«{parametro.etiqueta}» debe ser un número."}
                ) from error

        if parametro.tipo == TipoDato.LISTA and parametro.opciones:
            if texto not in [str(opcion) for opcion in parametro.opciones]:
                permitidos = ", ".join(str(opcion) for opcion in parametro.opciones)
                raise ValidationError(
                    {parametro.clave: f"Valor no permitido. Opciones: {permitidos}."}
                )
        return texto


class ServicioCamposPersonalizados:
    """
    Campos que el usuario define desde la interfaz y cuelga de cualquier modelo.

    Las tres apps funcionales usan esta clase y nada más de esta app:

    ``campos_de(entidad, categoria)``  definiciones activas.
    ``valores_de(objeto)``             valores guardados de un objeto.
    ``guardar_valores(objeto, datos)`` persiste lo que llega del formulario.
    ``validar(entidad, datos)``        comprueba requeridos y tipos.
    """

    # -- Lectura ------------------------------------------------------------
    @staticmethod
    def campos_de(entidad: str, categoria: str = "") -> list[DefinicionCampo]:
        """Devuelve las definiciones activas de la entidad, ya ordenadas."""
        return list(RepositorioDefinicionesCampo.para(entidad, categoria))

    @staticmethod
    def valores_de(objeto: Any, entidad: str = "") -> dict[str, Any]:
        """
        Devuelve ``{clave: valor}`` de los campos personalizados de un objeto.

        :param objeto: cualquier instancia con ``pk``.
        :param entidad: nombre lógico; si se omite se usa el del modelo.
        """
        nombre_entidad = entidad or objeto.__class__.__name__
        return {
            valor.definicion.clave: valor.valor
            for valor in RepositorioValoresCampo.de_objeto(nombre_entidad, str(objeto.pk))
        }

    @staticmethod
    def valores_con_etiqueta(objeto: Any, entidad: str = "",
                             categoria: str = "") -> list[dict[str, Any]]:
        """Devuelve los campos con su etiqueta y valor, listos para pintar en pantalla."""
        nombre_entidad = entidad or objeto.__class__.__name__
        guardados = ServicioCamposPersonalizados.valores_de(objeto, nombre_entidad)
        salida = []
        for definicion in ServicioCamposPersonalizados.campos_de(nombre_entidad, categoria):
            salida.append(
                {
                    "clave": definicion.clave,
                    "etiqueta": definicion.etiqueta,
                    "tipo": definicion.tipo,
                    "valor": guardados.get(definicion.clave),
                }
            )
        return salida

    # -- Validación ---------------------------------------------------------
    @staticmethod
    def validar(entidad: str, datos: dict[str, Any], categoria: str = "") -> dict[str, Any]:
        """
        Valida los datos de los campos personalizados del lado del servidor.

        La validación del navegador es comodidad; esta es la que manda
        (Seguridad #9 del brief).

        :returns: diccionario con los valores ya convertidos a su tipo.
        :raises ValidationError: con un error por cada campo que falle.
        """
        errores: dict[str, list[str]] = {}
        limpios: dict[str, Any] = {}

        for definicion in ServicioCamposPersonalizados.campos_de(entidad, categoria):
            crudo = datos.get(definicion.clave)
            vacio = crudo in (None, "", [])

            if definicion.requerido and vacio and definicion.tipo != TipoDato.BOOLEANO:
                errores.setdefault(definicion.clave, []).append(
                    f"«{definicion.etiqueta}» es obligatorio."
                )
                continue

            if vacio:
                limpios[definicion.clave] = None
                continue

            try:
                limpios[definicion.clave] = ServicioCamposPersonalizados._convertir(
                    definicion, crudo
                )
            except ValidationError as error:
                errores.setdefault(definicion.clave, []).extend(error.messages)

        if errores:
            raise ValidationError(errores)
        return limpios

    @staticmethod
    def _convertir(definicion: DefinicionCampo, crudo: Any) -> Any:
        """
        Convierte un valor crudo del formulario al tipo del campo.

        :raises ValidationError: si el valor no corresponde al tipo.
        """
        tipo = definicion.tipo

        if tipo == TipoDato.BOOLEANO:
            return str(crudo).strip().lower() in {"1", "true", "on", "si", "sí"}

        if tipo == TipoDato.NUMERO:
            try:
                return int(str(crudo).strip())
            except (TypeError, ValueError) as error:
                raise ValidationError(
                    f"«{definicion.etiqueta}» debe ser un número entero."
                ) from error

        if tipo == TipoDato.DECIMAL:
            try:
                return Decimal(str(crudo).strip().replace(",", ""))
            except (InvalidOperation, TypeError, ValueError) as error:
                raise ValidationError(f"«{definicion.etiqueta}» debe ser un número.") from error

        if tipo == TipoDato.FECHA:
            if isinstance(crudo, dt.date):
                return crudo
            for formato in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return dt.datetime.strptime(str(crudo).strip(), formato).date()
                except ValueError:
                    continue
            raise ValidationError(f"«{definicion.etiqueta}» debe ser una fecha válida.")

        if tipo == TipoDato.LISTA:
            permitidos = [str(opcion) for opcion in definicion.opciones or []]
            texto = str(crudo).strip()
            if permitidos and texto not in permitidos:
                raise ValidationError(
                    f"«{definicion.etiqueta}»: la opción «{texto}» no está permitida."
                )
            return texto

        if tipo == TipoDato.LISTA_MULTIPLE:
            seleccion = crudo if isinstance(crudo, list | tuple) else [crudo]
            permitidos = [str(opcion) for opcion in definicion.opciones or []]
            elegidos = [str(item).strip() for item in seleccion if str(item).strip()]
            invalidos = [item for item in elegidos if permitidos and item not in permitidos]
            if invalidos:
                raise ValidationError(
                    f"«{definicion.etiqueta}»: opciones no permitidas: {', '.join(invalidos)}."
                )
            return elegidos

        if tipo == TipoDato.USUARIO:
            try:
                return int(str(crudo).strip())
            except (TypeError, ValueError) as error:
                raise ValidationError(f"«{definicion.etiqueta}»: usuario inválido.") from error

        return str(crudo).strip()

    # -- Escritura ----------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def guardar_valores(objeto: Any, datos: dict[str, Any], entidad: str = "",
                        categoria: str = "") -> dict[str, Any]:
        """
        Valida y guarda los campos personalizados de un objeto.

        :param objeto: instancia ya guardada (necesita ``pk``).
        :param datos: lo que llega del formulario.
        :returns: diccionario con los valores guardados.
        :raises ValidationError: si algún campo no pasa la validación.
        """
        nombre_entidad = entidad or objeto.__class__.__name__
        limpios = ServicioCamposPersonalizados.validar(nombre_entidad, datos, categoria)

        guardadas = []
        for definicion in ServicioCamposPersonalizados.campos_de(nombre_entidad, categoria):
            if definicion.clave not in limpios:
                continue
            RepositorioValoresCampo.guardar(
                definicion,
                str(objeto.pk),
                ServicioCamposPersonalizados._columnas(definicion, limpios[definicion.clave]),
            )
            guardadas.append(definicion.clave)

        # Punto 9.7 del brief: toda acción deja rastro. Un solo registro por
        # operación, con las claves tocadas — no uno por campo, que llenaría la
        # auditoría de ruido cada vez que se guarda un artículo.
        if guardadas:
            ServicioAuditoria.registrar(
                entidad=nombre_entidad,
                entidad_id=objeto.pk,
                accion=RegistroAuditoria.Accion.EDITAR,
                detalle={"accion_dominio": "campos_personalizados", "campos": sorted(guardadas)},
            )
        return limpios

    @staticmethod
    def _columnas(definicion: DefinicionCampo, valor: Any) -> dict[str, Any]:
        """Reparte un valor en las columnas tipadas de ``ValorCampo``."""
        columnas: dict[str, Any] = {
            "valor_texto": "",
            "valor_numero": None,
            "valor_fecha": None,
            "valor_bool": None,
        }
        if valor is None:
            return columnas

        tipo = definicion.tipo
        if tipo == TipoDato.BOOLEANO:
            columnas["valor_bool"] = bool(valor)
        elif tipo in {TipoDato.NUMERO, TipoDato.DECIMAL}:
            columnas["valor_numero"] = Decimal(str(valor))
        elif tipo == TipoDato.FECHA:
            columnas["valor_fecha"] = valor
        elif tipo == TipoDato.LISTA_MULTIPLE:
            columnas["valor_texto"] = ",".join(str(item) for item in valor)
        else:
            columnas["valor_texto"] = str(valor)
        return columnas

    @staticmethod
    @transaction.atomic
    def borrar_valores(objeto: Any, entidad: str = "") -> int:
        """Elimina los valores personalizados de un objeto que se da de baja."""
        nombre_entidad = entidad or objeto.__class__.__name__
        borrados = RepositorioValoresCampo.borrar_de_objeto(nombre_entidad, str(objeto.pk))
        if borrados:
            ServicioAuditoria.registrar(
                entidad=nombre_entidad,
                entidad_id=objeto.pk,
                accion=RegistroAuditoria.Accion.ELIMINAR,
                detalle={"accion_dominio": "campos_personalizados", "borrados": borrados},
            )
        return borrados


class ServicioDefinicionesCampo:
    """Alta, edición, reordenamiento y baja de las definiciones de campo."""

    @staticmethod
    def listar(entidad: str = "") -> Any:
        """Devuelve las definiciones, filtradas por entidad si se indica."""
        return RepositorioDefinicionesCampo.listar(entidad=entidad)

    @staticmethod
    def obtener(definicion_id: int) -> DefinicionCampo | None:
        """Devuelve una definición por su identificador."""
        return RepositorioDefinicionesCampo.obtener(definicion_id)

    @staticmethod
    def entidades() -> list[str]:
        """Devuelve las entidades que ya tienen campos definidos."""
        return RepositorioDefinicionesCampo.entidades()

    @staticmethod
    @transaction.atomic
    def crear(**datos) -> DefinicionCampo:
        """
        Crea una definición de campo.

        :raises ValidationError: si la clave ya existe en esa entidad y categoría.
        """
        entidad = datos["entidad"].strip()
        categoria = (datos.get("categoria") or "").strip()
        clave = datos["clave"].strip()

        if RepositorioDefinicionesCampo.existe_clave(entidad, categoria, clave):
            raise ValidationError({"clave": "Ya existe un campo con esa clave en esa entidad."})

        definicion = DefinicionCampo.objects.create(
            entidad=entidad,
            categoria=categoria,
            clave=clave,
            etiqueta=datos["etiqueta"].strip(),
            tipo=datos["tipo"],
            requerido=bool(datos.get("requerido")),
            orden=datos.get("orden") or 100,
            opciones=ServicioDefinicionesCampo._limpiar_opciones(datos.get("opciones")),
            ayuda=(datos.get("ayuda") or "").strip(),
            activo=bool(datos.get("activo", True)),
        )
        ServicioAuditoria.registrar(
            entidad="DefinicionCampo",
            entidad_id=definicion.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"entidad": entidad, "clave": clave, "tipo": definicion.tipo},
        )
        return definicion

    @staticmethod
    @transaction.atomic
    def actualizar(definicion: DefinicionCampo, **datos) -> DefinicionCampo:
        """
        Actualiza una definición de campo.

        La entidad y la clave no cambian: los valores ya guardados dependen de
        ellas. Para renombrar se crea un campo nuevo y se desactiva el viejo.
        """
        antes = {
            "etiqueta": definicion.etiqueta,
            "tipo": definicion.tipo,
            "requerido": definicion.requerido,
            "opciones": definicion.opciones,
            "ayuda": definicion.ayuda,
            "activo": definicion.activo,
        }
        definicion.etiqueta = datos["etiqueta"].strip()
        definicion.tipo = datos["tipo"]
        definicion.requerido = bool(datos.get("requerido"))
        definicion.opciones = ServicioDefinicionesCampo._limpiar_opciones(datos.get("opciones"))
        definicion.ayuda = (datos.get("ayuda") or "").strip()
        definicion.activo = bool(datos.get("activo", True))
        definicion.save()

        despues = {
            "etiqueta": definicion.etiqueta,
            "tipo": definicion.tipo,
            "requerido": definicion.requerido,
            "opciones": definicion.opciones,
            "ayuda": definicion.ayuda,
            "activo": definicion.activo,
        }
        ServicioAuditoria.registrar(
            entidad="DefinicionCampo",
            entidad_id=definicion.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle={
                clave: {"antes": antes[clave], "despues": valor}
                for clave, valor in despues.items()
                if antes[clave] != valor
            },
        )
        return definicion

    @staticmethod
    @transaction.atomic
    def reordenar(identificadores: Iterable[int]) -> None:
        """Guarda el orden que dejó el usuario al arrastrar las filas."""
        pares = [(int(valor), (posicion + 1) * 10)
                 for posicion, valor in enumerate(identificadores)]
        RepositorioDefinicionesCampo.fijar_orden(pares)
        ServicioAuditoria.registrar(
            entidad="DefinicionCampo",
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"reordenado": [identificador for identificador, _ in pares]},
        )

    @staticmethod
    def _limpiar_opciones(crudo: Any) -> list[str]:
        """Convierte el texto de opciones (una por línea) en una lista limpia."""
        if crudo in (None, ""):
            return []
        if isinstance(crudo, list | tuple):
            return [str(item).strip() for item in crudo if str(item).strip()]
        return [linea.strip() for linea in str(crudo).splitlines() if linea.strip()]
