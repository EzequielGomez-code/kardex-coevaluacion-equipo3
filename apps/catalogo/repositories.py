"""
Repositorios del catálogo.

Única capa que consulta el ORM de estos modelos. Sin reglas de negocio.
"""

from __future__ import annotations

from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Concat, Substr

from apps.catalogo.models import (
    Articulo,
    Categoria,
    Marca,
    Proveedor,
    ProveedorArticulo,
    UnidadMedida,
)


class RepositorioCategorias:
    """Acceso a datos del árbol de categorías."""

    @staticmethod
    def arbol(solo_activas: bool = False) -> QuerySet[Categoria]:
        """Devuelve el árbol completo, ya en el orden en que se pinta en pantalla."""
        consulta = Categoria.objects.select_related("padre")
        if solo_activas:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("ruta")

    @staticmethod
    def obtener(categoria_id: int) -> Categoria | None:
        """Devuelve una categoría por su identificador, o ``None``."""
        return Categoria.objects.select_related("padre").filter(pk=categoria_id).first()

    @staticmethod
    def obtener_por_codigo(codigo: str) -> Categoria | None:
        """Devuelve una categoría por su código exacto, o ``None``."""
        return Categoria.objects.filter(codigo=codigo).first()

    @staticmethod
    def hijas_directas(categoria: Categoria | None) -> QuerySet[Categoria]:
        """Devuelve las hijas inmediatas de una categoría (o las raíces si es ``None``)."""
        return Categoria.objects.filter(padre=categoria).order_by("orden", "codigo")

    @staticmethod
    def descendientes(categoria: Categoria) -> QuerySet[Categoria]:
        """Devuelve todas las categorías bajo esta, sin incluirla."""
        return Categoria.objects.filter(ruta__startswith=f"{categoria.ruta}.")

    @staticmethod
    def existe_codigo(padre_id: int | None, codigo: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otra categoría con ese código bajo el mismo padre."""
        consulta = Categoria.objects.filter(padre_id=padre_id, codigo__iexact=codigo)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def reescribir_rutas_del_subarbol(
        ruta_vieja: str, ruta_nueva: str, delta_nivel: int
    ) -> None:
        """
        Reescribe en un solo UPDATE la ruta de un nodo y todos sus descendientes.

        Se usa un prefijo intermedio (ver ``ServicioCategorias.mover``) para
        que la unicidad de ``ruta`` nunca choque a mitad de la operación.
        """
        Categoria.objects.filter(ruta__startswith=f"{ruta_vieja}.").update(
            ruta=Concat(Value(ruta_nueva), Substr("ruta", len(ruta_vieja) + 1)),
            nivel=F("nivel") + delta_nivel,
        )
        Categoria.objects.filter(ruta=ruta_vieja).update(ruta=ruta_nueva, nivel=F("nivel"))

    @staticmethod
    def fijar_orden(pares: list[tuple[int, int]]) -> None:
        """Guarda el nuevo orden a partir de pares ``(id, orden)``."""
        for categoria_id, orden in pares:
            Categoria.objects.filter(pk=categoria_id).update(orden=orden)

    @staticmethod
    def tiene_articulos(categoria: Categoria) -> bool:
        """Indica si la categoría (o sus hijas) tienen artículos asignados."""
        return Articulo.objects.filter(
            Q(categoria=categoria) | Q(categoria__ruta__startswith=f"{categoria.ruta}.")
        ).exists()


class RepositorioMarcas:
    """Acceso a datos de :class:`~apps.catalogo.models.Marca`."""

    @staticmethod
    def listar(solo_activas: bool = False) -> QuerySet[Marca]:
        """Devuelve las marcas del catálogo."""
        consulta = Marca.objects.all()
        if solo_activas:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("nombre")

    @staticmethod
    def obtener(marca_id: int) -> Marca | None:
        """Devuelve una marca por su identificador, o ``None``."""
        return Marca.objects.filter(pk=marca_id).first()


class RepositorioUnidadesMedida:
    """Acceso a datos de :class:`~apps.catalogo.models.UnidadMedida`."""

    @staticmethod
    def listar(solo_activas: bool = False) -> QuerySet[UnidadMedida]:
        """Devuelve las unidades de medida del catálogo."""
        consulta = UnidadMedida.objects.all()
        if solo_activas:
            consulta = consulta.filter(activo=True)
        return consulta.order_by("codigo")

    @staticmethod
    def obtener(unidad_id: int) -> UnidadMedida | None:
        """Devuelve una unidad de medida por su identificador, o ``None``."""
        return UnidadMedida.objects.filter(pk=unidad_id).first()


class RepositorioArticulos:
    """Acceso a datos de :class:`~apps.catalogo.models.Articulo`."""

    @staticmethod
    def listar(
        busqueda: str = "", categoria_id: int | None = None, marca_id: int | None = None,
        estado: str = "",
    ) -> QuerySet[Articulo]:
        """Devuelve los artículos filtrados, con categoría, marca y unidad precargadas."""
        consulta = Articulo.objects.select_related("categoria", "marca", "unidad")
        if busqueda:
            consulta = consulta.filter(
                Q(sku__icontains=busqueda)
                | Q(nombre__icontains=busqueda)
                | Q(codigo_barras__icontains=busqueda)
            )
        if categoria_id:
            categoria = Categoria.objects.filter(pk=categoria_id).first()
            if categoria:
                consulta = consulta.filter(
                    Q(categoria=categoria) | Q(categoria__ruta__startswith=f"{categoria.ruta}.")
                )
        if marca_id:
            consulta = consulta.filter(marca_id=marca_id)
        if estado == "activo":
            consulta = consulta.filter(activo=True)
        elif estado == "inactivo":
            consulta = consulta.filter(activo=False)
        return consulta.order_by("nombre")

    @staticmethod
    def obtener(articulo_id: int) -> Articulo | None:
        """Devuelve un artículo por su identificador, con sus relaciones precargadas."""
        return (
            Articulo.objects.select_related("categoria", "marca", "unidad")
            .filter(pk=articulo_id)
            .first()
        )

    @staticmethod
    def existe_sku(sku: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro artículo con ese SKU."""
        consulta = Articulo.objects.filter(sku__iexact=sku)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def existe_codigo_barras(codigo_barras: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro artículo con ese código de barras."""
        if not codigo_barras:
            return False
        consulta = Articulo.objects.filter(codigo_barras=codigo_barras)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def tiene_movimientos(articulo: Articulo) -> bool:
        """Indica si el artículo ya tiene líneas de movimiento registradas."""
        return articulo.lineas.exists() if hasattr(articulo, "lineas") else False


class RepositorioTerceros:
    """Acceso a datos compartido entre :class:`Proveedor` y :class:`Cliente`."""

    @staticmethod
    def listar(modelo, busqueda: str = "", estado: str = ""):
        """Devuelve proveedores o clientes filtrados, según el modelo recibido."""
        consulta = modelo.objects.all()
        if busqueda:
            consulta = consulta.filter(
                Q(codigo__icontains=busqueda)
                | Q(razon_social__icontains=busqueda)
                | Q(nombre_comercial__icontains=busqueda)
                | Q(rnc__icontains=busqueda)
            )
        if estado == "activo":
            consulta = consulta.filter(activo=True)
        elif estado == "inactivo":
            consulta = consulta.filter(activo=False)
        return consulta.order_by("razon_social")

    @staticmethod
    def obtener(modelo, identificador: int):
        """Devuelve un proveedor o cliente por su identificador, o ``None``."""
        return modelo.objects.filter(pk=identificador).first()

    @staticmethod
    def existe_codigo(modelo, codigo: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro registro de ese modelo con ese código."""
        consulta = modelo.objects.filter(codigo__iexact=codigo)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()

    @staticmethod
    def existe_rnc(modelo, rnc: str, excluir_id: int | None = None) -> bool:
        """Indica si ya hay otro registro de ese modelo con ese RNC."""
        if not rnc:
            return False
        consulta = modelo.objects.filter(rnc=rnc)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()


class RepositorioProveedorArticulo:
    """Acceso a datos de :class:`~apps.catalogo.models.ProveedorArticulo`."""

    @staticmethod
    def de_articulo(articulo: Articulo) -> QuerySet[ProveedorArticulo]:
        """Devuelve los proveedores de un artículo, con el preferido primero."""
        return (
            ProveedorArticulo.objects.select_related("proveedor")
            .filter(articulo=articulo)
            .order_by("-es_preferido", "precio_compra")
        )

    @staticmethod
    def de_proveedor(proveedor: Proveedor) -> QuerySet[ProveedorArticulo]:
        """Devuelve los artículos que suministra un proveedor."""
        return (
            ProveedorArticulo.objects.select_related("articulo")
            .filter(proveedor=proveedor)
            .order_by("articulo__nombre")
        )

    @staticmethod
    def obtener(relacion_id: int) -> ProveedorArticulo | None:
        """Devuelve una relación proveedor-artículo por su identificador."""
        return (
            ProveedorArticulo.objects.select_related("proveedor", "articulo")
            .filter(pk=relacion_id)
            .first()
        )

    @staticmethod
    def existe(proveedor: Proveedor, articulo: Articulo, excluir_id: int | None = None) -> bool:
        """Indica si ya existe una relación entre ese proveedor y ese artículo."""
        consulta = ProveedorArticulo.objects.filter(proveedor=proveedor, articulo=articulo)
        if excluir_id:
            consulta = consulta.exclude(pk=excluir_id)
        return consulta.exists()
