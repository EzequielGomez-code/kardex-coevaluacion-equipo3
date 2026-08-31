"""
Servicios del catálogo.

``ServicioCategorias`` concentra la aritmética del árbol: crear, reordenar y
mover categorías reescribiendo su ``ruta`` materializada. El resto son
servicios de alta y edición más convencionales.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalogo.models import (
    Articulo,
    Categoria,
    Cliente,
    Marca,
    Proveedor,
    ProveedorArticulo,
    UnidadMedida,
)
from apps.catalogo.repositories import (
    RepositorioArticulos,
    RepositorioCategorias,
    RepositorioMarcas,
    RepositorioProveedorArticulo,
    RepositorioTerceros,
    RepositorioUnidadesMedida,
)
from apps.configuracion.services import ServicioCamposPersonalizados, ServicioParametros
from apps.nucleo.models import RegistroAuditoria
from apps.nucleo.services import ServicioAuditoria

ANCHO_SEGMENTO = 4  # dígitos por nivel de la ruta materializada
PROFUNDIDAD_MAXIMA = 5
PREFIJO_TEMPORAL = "~"  # ordena después de dígitos y punto: evita choques de unicidad


def _segmento(orden: int) -> str:
    """Convierte un entero de orden en un segmento de ruta de ancho fijo."""
    return str(orden).zfill(ANCHO_SEGMENTO)


class ServicioCategorias:
    """Alta, edición, reordenamiento y traslado de categorías en el árbol."""

    @staticmethod
    def arbol(solo_activas: bool = False) -> list[Categoria]:
        """Devuelve el árbol completo en el orden en que se pinta en pantalla."""
        return list(RepositorioCategorias.arbol(solo_activas=solo_activas))

    @staticmethod
    def obtener(categoria_id: int) -> Categoria | None:
        """Devuelve una categoría por su identificador."""
        return RepositorioCategorias.obtener(categoria_id)

    @staticmethod
    def hijas_directas(categoria: Categoria | None) -> Any:
        """Devuelve las hijas inmediatas de una categoría, o las raíces si es ``None``."""
        return RepositorioCategorias.hijas_directas(categoria)

    @staticmethod
    @transaction.atomic
    def crear(codigo: str, nombre: str, descripcion: str, padre: Categoria | None,
              icono: str = "catalogo") -> Categoria:
        """
        Crea una categoría al final de las hijas de ``padre`` (o de la raíz).

        :raises ValidationError: si el código ya existe bajo ese padre, o si
            la profundidad supera el máximo permitido.
        """
        codigo = codigo.strip().upper()
        if RepositorioCategorias.existe_codigo(padre.pk if padre else None, codigo):
            raise ValidationError({"codigo": "Ya existe una categoría con ese código aquí."})

        nivel = (padre.nivel + 1) if padre else 0
        if nivel > PROFUNDIDAD_MAXIMA:
            raise ValidationError(
                f"No se pueden crear más de {PROFUNDIDAD_MAXIMA} niveles de categorías."
            )

        hermanas = RepositorioCategorias.hijas_directas(padre)
        ultimo_orden = hermanas.order_by("-orden").values_list("orden", flat=True).first() or 0
        orden = ultimo_orden + 10

        prefijo = f"{padre.ruta}." if padre else ""
        ruta = f"{prefijo}{_segmento(orden)}"

        categoria = Categoria.objects.create(
            codigo=codigo, nombre=nombre.strip(), descripcion=descripcion.strip(),
            padre=padre, ruta=ruta, nivel=nivel, orden=orden, icono=icono,
        )
        ServicioAuditoria.registrar(
            entidad="Categoria", entidad_id=categoria.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"codigo": categoria.codigo, "nombre": categoria.nombre,
                    "padre": padre.codigo if padre else None},
        )
        return categoria

    @staticmethod
    @transaction.atomic
    def actualizar(categoria: Categoria, nombre: str, descripcion: str,
                   icono: str, activo: bool) -> Categoria:
        """Actualiza una categoría. El código y la posición en el árbol no se tocan aquí."""
        antes = {"nombre": categoria.nombre, "descripcion": categoria.descripcion,
                "activo": categoria.activo}
        categoria.nombre = nombre.strip()
        categoria.descripcion = descripcion.strip()
        categoria.icono = icono
        categoria.activo = activo
        categoria.save()

        despues = {"nombre": categoria.nombre, "descripcion": categoria.descripcion,
                  "activo": categoria.activo}
        ServicioAuditoria.registrar(
            entidad="Categoria", entidad_id=categoria.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle={k: {"antes": antes[k], "despues": v} for k, v in despues.items()
                    if antes[k] != v},
        )
        return categoria

    @staticmethod
    @transaction.atomic
    def reordenar(padre_id: int | None, identificadores: list[int]) -> None:
        """
        Guarda el nuevo orden entre las hermanas de un mismo padre.

        Reescribe también la ruta de cada una (y la de sus descendientes),
        porque la ruta codifica el orden.

        :raises ValidationError: si algún identificador no es realmente una
            hija directa del padre indicado — evita que una petición
            manipulada reordene nodos de otra rama del árbol.
        """
        padre = Categoria.objects.filter(pk=padre_id).first() if padre_id else None
        hijas_reales = set(
            RepositorioCategorias.hijas_directas(padre).values_list("pk", flat=True)
        )
        if set(identificadores) != hijas_reales:
            raise ValidationError("La lista de categorías no coincide con las hijas de ese nodo.")

        prefijo = f"{padre.ruta}." if padre else ""

        # Primera pasada: todas a un prefijo temporal, para que la unicidad de
        # «ruta» nunca choque a mitad de camino con la ruta definitiva de otra.
        # Se usa el mismo reescritor en cascada que «mover»: mueve la fila de
        # la categoría Y las de sus descendientes, no solo la primera.
        for categoria_id in identificadores:
            categoria = Categoria.objects.get(pk=categoria_id)
            ruta_temporal = f"{PREFIJO_TEMPORAL}{categoria.pk}"
            RepositorioCategorias.reescribir_rutas_del_subarbol(categoria.ruta, ruta_temporal, 0)

        for posicion, categoria_id in enumerate(identificadores):
            orden = (posicion + 1) * 10
            categoria = Categoria.objects.get(pk=categoria_id)  # ya con la ruta temporal
            ruta_nueva = f"{prefijo}{_segmento(orden)}"
            RepositorioCategorias.reescribir_rutas_del_subarbol(categoria.ruta, ruta_nueva, 0)
            Categoria.objects.filter(pk=categoria_id).update(orden=orden)

        ServicioAuditoria.registrar(
            entidad="Categoria", accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "reordenar", "padre": padre.codigo if padre else None,
                    "orden": identificadores},
        )

    @staticmethod
    @transaction.atomic
    def mover(categoria: Categoria, nuevo_padre: Categoria | None) -> Categoria:
        """
        Mueve una categoría (con todo su subárbol) a otro padre.

        :raises ValidationError: si el destino es la propia categoría, un
            descendiente suyo (crearía un ciclo), o si excede la profundidad
            máxima.
        """
        if nuevo_padre and nuevo_padre.pk == categoria.pk:
            raise ValidationError("Una categoría no puede ser su propio padre.")
        if nuevo_padre and nuevo_padre.ruta.startswith(f"{categoria.ruta}."):
            raise ValidationError("No se puede mover una categoría dentro de su propia rama.")

        nuevo_nivel = (nuevo_padre.nivel + 1) if nuevo_padre else 0
        profundidad_subarbol = categoria.ruta.count(".")
        if nuevo_nivel + profundidad_subarbol > PROFUNDIDAD_MAXIMA:
            raise ValidationError(
                f"El traslado dejaría categorías por debajo del nivel {PROFUNDIDAD_MAXIMA}."
            )

        if RepositorioCategorias.existe_codigo(
            nuevo_padre.pk if nuevo_padre else None, categoria.codigo, excluir_id=categoria.pk
        ):
            raise ValidationError(
                {"codigo": "Ya existe una categoría con ese código en el destino."}
            )

        hermanas_destino = RepositorioCategorias.hijas_directas(nuevo_padre)
        ultimo_orden = (
            hermanas_destino.order_by("-orden").values_list("orden", flat=True).first() or 0
        )
        orden_nuevo = ultimo_orden + 10
        prefijo_destino = f"{nuevo_padre.ruta}." if nuevo_padre else ""

        ruta_vieja = categoria.ruta
        ruta_temporal = f"{PREFIJO_TEMPORAL}{categoria.pk}"
        ruta_nueva = f"{prefijo_destino}{_segmento(orden_nuevo)}"
        delta_nivel = nuevo_nivel - categoria.nivel

        RepositorioCategorias.reescribir_rutas_del_subarbol(ruta_vieja, ruta_temporal, 0)
        RepositorioCategorias.reescribir_rutas_del_subarbol(
            ruta_temporal, ruta_nueva, delta_nivel
        )
        Categoria.objects.filter(pk=categoria.pk).update(
            padre=nuevo_padre, orden=orden_nuevo
        )

        categoria.refresh_from_db()
        ServicioAuditoria.registrar(
            entidad="Categoria", entidad_id=categoria.pk,
            accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"accion_dominio": "mover", "codigo": categoria.codigo,
                    "nuevo_padre": nuevo_padre.codigo if nuevo_padre else None},
        )
        return categoria

    @staticmethod
    @transaction.atomic
    def eliminar(categoria: Categoria) -> None:
        """
        Elimina una categoría vacía.

        :raises ValidationError: si tiene hijas o artículos asignados.
        """
        if RepositorioCategorias.hijas_directas(categoria).exists():
            raise ValidationError("Esta categoría tiene subcategorías. Elimínelas primero.")
        if RepositorioCategorias.tiene_articulos(categoria):
            raise ValidationError("Esta categoría tiene artículos asignados.")

        identificador, codigo = categoria.pk, categoria.codigo
        categoria.delete()
        ServicioAuditoria.registrar(
            entidad="Categoria", entidad_id=identificador,
            accion=RegistroAuditoria.Accion.ELIMINAR, detalle={"codigo": codigo},
        )


class ServicioMarcas:
    """Alta y edición de marcas."""

    @staticmethod
    def listar(solo_activas: bool = False) -> Any:
        """Devuelve las marcas del catálogo."""
        return RepositorioMarcas.listar(solo_activas=solo_activas)

    @staticmethod
    def obtener(marca_id: int) -> Marca | None:
        """Devuelve una marca por su identificador."""
        return RepositorioMarcas.obtener(marca_id)

    @staticmethod
    @transaction.atomic
    def crear(nombre: str, pais: str, sitio_web: str) -> Marca:
        """Crea una marca."""
        marca = Marca.objects.create(
            nombre=nombre.strip(), pais=pais.strip(), sitio_web=sitio_web.strip()
        )
        ServicioAuditoria.registrar(
            entidad="Marca", entidad_id=marca.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"nombre": marca.nombre},
        )
        return marca

    @staticmethod
    @transaction.atomic
    def actualizar(marca: Marca, nombre: str, pais: str, sitio_web: str, activo: bool) -> Marca:
        """Actualiza una marca."""
        marca.nombre = nombre.strip()
        marca.pais = pais.strip()
        marca.sitio_web = sitio_web.strip()
        marca.activo = activo
        marca.save()
        ServicioAuditoria.registrar(
            entidad="Marca", entidad_id=marca.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"nombre": marca.nombre},
        )
        return marca


class ServicioUnidadesMedida:
    """Alta y edición de unidades de medida."""

    @staticmethod
    def listar(solo_activas: bool = False) -> Any:
        """Devuelve las unidades de medida del catálogo."""
        return RepositorioUnidadesMedida.listar(solo_activas=solo_activas)

    @staticmethod
    def obtener(unidad_id: int) -> UnidadMedida | None:
        """Devuelve una unidad de medida por su identificador."""
        return RepositorioUnidadesMedida.obtener(unidad_id)

    @staticmethod
    @transaction.atomic
    def crear(codigo: str, nombre: str, simbolo: str, permite_decimales: bool) -> UnidadMedida:
        """Crea una unidad de medida."""
        unidad = UnidadMedida.objects.create(
            codigo=codigo.strip(), nombre=nombre.strip(), simbolo=simbolo.strip(),
            permite_decimales=permite_decimales,
        )
        ServicioAuditoria.registrar(
            entidad="UnidadMedida", entidad_id=unidad.pk,
            accion=RegistroAuditoria.Accion.CREAR, detalle={"codigo": unidad.codigo},
        )
        return unidad

    @staticmethod
    @transaction.atomic
    def actualizar(unidad: UnidadMedida, nombre: str, simbolo: str,
                   permite_decimales: bool, activo: bool) -> UnidadMedida:
        """Actualiza una unidad de medida. El código no se toca aquí."""
        unidad.nombre = nombre.strip()
        unidad.simbolo = simbolo.strip()
        unidad.permite_decimales = permite_decimales
        unidad.activo = activo
        unidad.save()
        ServicioAuditoria.registrar(
            entidad="UnidadMedida", entidad_id=unidad.pk,
            accion=RegistroAuditoria.Accion.EDITAR, detalle={"codigo": unidad.codigo},
        )
        return unidad


class ServicioArticulos:
    """Alta, edición y baja de artículos, con generación de SKU."""

    @staticmethod
    def listar(**filtros) -> Any:
        """Devuelve los artículos filtrados."""
        return RepositorioArticulos.listar(**filtros)

    @staticmethod
    def obtener(articulo_id: int) -> Articulo | None:
        """Devuelve un artículo por su identificador."""
        return RepositorioArticulos.obtener(articulo_id)

    @staticmethod
    def campos_de_categoria(categoria: Categoria) -> list:
        """Devuelve los campos personalizados que aplican a esta categoría."""
        return ServicioCamposPersonalizados.campos_de("Articulo", categoria.codigo)

    @staticmethod
    @transaction.atomic
    def generar_sku(categoria: Categoria) -> str:
        """
        Genera un SKU único a partir del formato configurable ``formato_sku``.

        Incrementa el contador de la categoría bajo bloqueo, para que dos
        artículos creados a la vez no reciban el mismo número.
        """
        formato = ServicioParametros.obtener("formato_sku", "{categoria}-{secuencia:05d}")

        # select_for_update es no-op en SQLite; en Postgres serializa el incremento.
        categoria_bloqueada = Categoria.objects.select_for_update().get(pk=categoria.pk)
        categoria_bloqueada.secuencia_sku += 1
        categoria_bloqueada.save(update_fields=["secuencia_sku"])

        try:
            sku = formato.format(
                categoria=categoria_bloqueada.codigo, secuencia=categoria_bloqueada.secuencia_sku
            )
        except (KeyError, ValueError, IndexError):
            # Una plantilla mal escrita no debe tumbar el alta de un artículo.
            sku = f"{categoria_bloqueada.codigo}-{categoria_bloqueada.secuencia_sku:05d}"

        if RepositorioArticulos.existe_sku(sku):
            sku = f"{sku}-{categoria_bloqueada.secuencia_sku}"
        return sku

    @staticmethod
    @transaction.atomic
    def crear(**datos) -> Articulo:
        """
        Crea un artículo. Si no se indica ``sku``, se genera con
        :meth:`generar_sku`.

        :raises ValidationError: si el SKU o el código de barras ya existen.
        """
        categoria = datos["categoria"]
        sku = (datos.get("sku") or "").strip().upper() or ServicioArticulos.generar_sku(categoria)

        if RepositorioArticulos.existe_sku(sku):
            raise ValidationError({"sku": "Ya existe un artículo con ese SKU."})

        codigo_barras = (datos.get("codigo_barras") or "").strip()
        if RepositorioArticulos.existe_codigo_barras(codigo_barras):
            raise ValidationError({"codigo_barras": "Ya existe un artículo con ese código de barras."})

        articulo = Articulo.objects.create(
            sku=sku,
            codigo_barras=codigo_barras,
            nombre=datos["nombre"].strip(),
            descripcion=(datos.get("descripcion") or "").strip(),
            categoria=categoria,
            marca=datos.get("marca"),
            unidad=datos["unidad"],
            es_inventariable=datos.get("es_inventariable", True),
            maneja_lotes=datos.get("maneja_lotes", True),
            maneja_vencimiento=datos.get("maneja_vencimiento", False),
            costo_referencia=datos.get("costo_referencia") or 0,
            precio_venta=datos.get("precio_venta") or 0,
            tasa_itbis=datos.get("tasa_itbis", 18),
            stock_minimo_defecto=datos.get("stock_minimo_defecto") or 5,
            activo=datos.get("activo", True),
        )
        ServicioAuditoria.registrar(
            entidad="Articulo", entidad_id=articulo.pk, accion=RegistroAuditoria.Accion.CREAR,
            detalle={"sku": articulo.sku, "nombre": articulo.nombre},
        )
        return articulo

    @staticmethod
    @transaction.atomic
    def actualizar(articulo: Articulo, **datos) -> Articulo:
        """Actualiza un artículo. El SKU no se toca aquí."""
        codigo_barras = (datos.get("codigo_barras") or "").strip()
        if RepositorioArticulos.existe_codigo_barras(codigo_barras, excluir_id=articulo.pk):
            raise ValidationError({"codigo_barras": "Ya existe un artículo con ese código de barras."})

        for campo in (
            "nombre", "descripcion", "categoria", "marca", "unidad", "es_inventariable",
            "maneja_lotes", "maneja_vencimiento", "costo_referencia", "precio_venta",
            "tasa_itbis", "stock_minimo_defecto", "activo",
        ):
            if campo in datos:
                valor = datos[campo]
                setattr(articulo, campo, valor.strip() if isinstance(valor, str) else valor)
        articulo.codigo_barras = codigo_barras
        articulo.save()

        ServicioAuditoria.registrar(
            entidad="Articulo", entidad_id=articulo.pk, accion=RegistroAuditoria.Accion.EDITAR,
            detalle={"sku": articulo.sku},
        )
        return articulo

    @staticmethod
    @transaction.atomic
    def dar_de_baja(articulo: Articulo) -> Articulo:
        """
        Da de baja un artículo: borrado duro solo si nunca tuvo movimientos.

        Si ya tiene historial, se desactiva en su lugar para no romper el
        kardex.
        """
        if RepositorioArticulos.tiene_movimientos(articulo):
            articulo.activo = False
            articulo.save(update_fields=["activo", "actualizado_en"])
            ServicioAuditoria.registrar(
                entidad="Articulo", entidad_id=articulo.pk,
                accion=RegistroAuditoria.Accion.EDITAR,
                detalle={"accion_dominio": "baja_logica", "sku": articulo.sku},
            )
            return articulo

        identificador, sku = articulo.pk, articulo.sku
        ServicioCamposPersonalizados.borrar_valores(articulo, entidad="Articulo")
        articulo.delete()
        ServicioAuditoria.registrar(
            entidad="Articulo", entidad_id=identificador,
            accion=RegistroAuditoria.Accion.ELIMINAR, detalle={"sku": sku},
        )
        return articulo


class _ServicioTercero:
    """
    Base común para :class:`ServicioProveedores` y :class:`ServicioClientes`.

    No se expone directamente: cada subclase fija su ``modelo`` y hereda el
    resto. Evita duplicar cuatro veces la misma alta/edición/baja.
    """

    modelo: type

    @classmethod
    def listar(cls, busqueda: str = "", estado: str = "") -> Any:
        """Devuelve los terceros filtrados."""
        return RepositorioTerceros.listar(cls.modelo, busqueda=busqueda, estado=estado)

    @classmethod
    def obtener(cls, identificador: int) -> Any:
        """Devuelve un tercero por su identificador."""
        return RepositorioTerceros.obtener(cls.modelo, identificador)

    @classmethod
    @transaction.atomic
    def crear(cls, **datos) -> Any:
        """
        Crea un proveedor o cliente.

        :raises ValidationError: si el código o el RNC ya existen.
        """
        codigo = datos["codigo"].strip().upper()
        if RepositorioTerceros.existe_codigo(cls.modelo, codigo):
            raise ValidationError({"codigo": "Ya existe un registro con ese código."})

        instancia = cls.modelo(
            codigo=codigo,
            razon_social=datos["razon_social"].strip(),
            nombre_comercial=(datos.get("nombre_comercial") or "").strip(),
            tipo_documento=datos.get("tipo_documento", "rnc"),
            rnc=datos.get("rnc", ""),
            telefono=(datos.get("telefono") or "").strip(),
            email=(datos.get("email") or "").strip(),
            direccion=(datos.get("direccion") or "").strip(),
            contacto=(datos.get("contacto") or "").strip(),
            dias_credito=datos.get("dias_credito") or 0,
            limite_credito=datos.get("limite_credito") or 0,
            notas=(datos.get("notas") or "").strip(),
            activo=datos.get("activo", True),
        )
        # validate_constraints=False: la unicidad del RNC la comprueba a mano
        # la línea de abajo, con un mensaje en español y no el nombre técnico
        # de la restricción de la base («No se cumple la restricción…»).
        instancia.full_clean(validate_constraints=False)
        if RepositorioTerceros.existe_rnc(cls.modelo, instancia.rnc):
            raise ValidationError({"rnc": "Ya existe un registro con ese RNC."})
        instancia.save()

        ServicioAuditoria.registrar(
            entidad=cls.modelo.__name__, entidad_id=instancia.pk,
            accion=RegistroAuditoria.Accion.CREAR,
            detalle={"codigo": instancia.codigo, "razon_social": instancia.razon_social},
        )
        return instancia

    @classmethod
    @transaction.atomic
    def actualizar(cls, instancia: Any, **datos) -> Any:
        """Actualiza un proveedor o cliente. El código no se toca aquí."""
        for campo in (
            "razon_social", "nombre_comercial", "tipo_documento", "rnc", "telefono", "email",
            "direccion", "contacto", "dias_credito", "limite_credito", "notas", "activo",
        ):
            if campo in datos:
                valor = datos[campo]
                setattr(instancia, campo, valor.strip() if isinstance(valor, str) else valor)

        instancia.full_clean(validate_constraints=False)
        if RepositorioTerceros.existe_rnc(cls.modelo, instancia.rnc, excluir_id=instancia.pk):
            raise ValidationError({"rnc": "Ya existe un registro con ese RNC."})
        instancia.save()

        ServicioAuditoria.registrar(
            entidad=cls.modelo.__name__, entidad_id=instancia.pk,
            accion=RegistroAuditoria.Accion.EDITAR, detalle={"codigo": instancia.codigo},
        )
        return instancia

    @classmethod
    @transaction.atomic
    def cambiar_estado(cls, instancia: Any, activo: bool) -> Any:
        """Activa o desactiva un proveedor o cliente."""
        instancia.activo = activo
        instancia.save(update_fields=["activo", "actualizado_en"])
        ServicioAuditoria.registrar(
            entidad=cls.modelo.__name__, entidad_id=instancia.pk,
            accion=RegistroAuditoria.Accion.EDITAR, detalle={"activo": activo},
        )
        return instancia


class ServicioProveedores(_ServicioTercero):
    """Alta, edición y baja de proveedores."""

    modelo = Proveedor

    @staticmethod
    def articulos_suministrados(proveedor: Proveedor) -> Any:
        """Devuelve los artículos que suministra un proveedor."""
        return RepositorioProveedorArticulo.de_proveedor(proveedor)

    @staticmethod
    @transaction.atomic
    def fijar_precio(proveedor: Proveedor, articulo: Articulo, **datos) -> ProveedorArticulo:
        """
        Crea o actualiza el precio de un proveedor para un artículo.

        :raises ValidationError: si ese proveedor ya está ligado a ese artículo
            y se intenta crear una segunda vez (usar la edición en su lugar).
        """
        relacion = ProveedorArticulo.objects.filter(proveedor=proveedor, articulo=articulo).first()
        creando = relacion is None
        if creando:
            relacion = ProveedorArticulo(proveedor=proveedor, articulo=articulo)

        relacion.codigo_proveedor = (datos.get("codigo_proveedor") or "").strip()
        relacion.precio_compra = datos["precio_compra"]
        relacion.tiempo_entrega_dias = datos.get("tiempo_entrega_dias") or 0
        relacion.cantidad_minima = datos.get("cantidad_minima") or 1
        relacion.activo = datos.get("activo", True)

        if datos.get("es_preferido"):
            ProveedorArticulo.objects.filter(articulo=articulo).exclude(
                pk=relacion.pk
            ).update(es_preferido=False)
            relacion.es_preferido = True
        else:
            relacion.es_preferido = False

        relacion.save()
        ServicioAuditoria.registrar(
            entidad="ProveedorArticulo", entidad_id=relacion.pk,
            accion=RegistroAuditoria.Accion.CREAR if creando else RegistroAuditoria.Accion.EDITAR,
            detalle={"proveedor": proveedor.codigo, "articulo": articulo.sku,
                    "precio_compra": str(relacion.precio_compra)},
        )
        return relacion

    @staticmethod
    @transaction.atomic
    def quitar_precio(relacion: ProveedorArticulo) -> None:
        """Elimina la relación de precio entre un proveedor y un artículo."""
        identificador = relacion.pk
        detalle = {"proveedor": relacion.proveedor.codigo, "articulo": relacion.articulo.sku}
        relacion.delete()
        ServicioAuditoria.registrar(
            entidad="ProveedorArticulo", entidad_id=identificador,
            accion=RegistroAuditoria.Accion.ELIMINAR, detalle=detalle,
        )


class ServicioClientes(_ServicioTercero):
    """Alta, edición y baja de clientes."""

    modelo = Cliente
