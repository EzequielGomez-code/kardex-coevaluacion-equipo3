"""
Comando de gestión: siembra datos de demostración realistas.

Separado de ``sembrar`` a propósito: ``build.sh`` corre ``sembrar`` en cada
despliegue, y nadie quiere 150 artículos y mil doscientos movimientos en una
instalación limpia (además, las pruebas afirman ``Almacen.objects.count() ==
2``). Este comando es opcional: para practicar en local y para el recorrido
de aceptación del brief contra la URL pública.

Para el grueso de los movimientos no se pasa por los servicios — auditar fila
por fila mil doscientas veces contra una base remota tarda minutos. Se arma
todo en listas de Python (con la aritmética PEPS resuelta con la misma
función ``planificar_consumo`` que usa la aplicación real) y se escribe con
``bulk_create``. Una media docena de movimientos sí pasan por
``ServicioMovimientos``, para dejar al menos algunos bien recientes y con
todo el circuito real (alertas incluidas) puesto a prueba.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.alertas.models import Alerta, ReglaAlerta, TipoRegla
from apps.alertas.services import ServicioEvaluador
from apps.catalogo.models import (
    Articulo,
    Categoria,
    Cliente,
    Marca,
    Proveedor,
    ProveedorArticulo,
    UnidadMedida,
)
from apps.catalogo.services import ServicioCategorias, ServicioClientes, ServicioProveedores
from apps.catalogo.validadores import PESOS_RNC_9
from apps.movimientos.models import (
    ConsumoLote,
    EstadoMovimiento,
    Existencia,
    Lote,
    Movimiento,
    MovimientoLinea,
    Naturaleza,
    TipoMovimiento,
)
from apps.movimientos.services import ServicioMovimientos
from apps.movimientos.valoracion import CUATRO_DECIMALES, METODO_PEPS, planificar_consumo
from apps.nucleo.models import Almacen, Usuario

SEMILLA = 20260831  # fija, para que la demo salga igual cada vez que se corre

UNIDADES = [
    ("UD", "Unidad", "ud", True),
    ("SC", "Saco", "sc", False),
    ("QQ", "Quintal", "qq", True),
    ("M", "Metro", "m", True),
    ("KG", "Kilogramo", "kg", True),
    ("GL", "Galón", "gal", True),
    ("CJ", "Caja", "cj", False),
    ("PZ", "Pieza", "pz", False),
    ("RL", "Rollo", "rl", False),
]

MARCAS = [
    "ProBuild", "FerroMax", "TitanFix", "Andina", "DuraTech",
    "ColorMix", "ElectroPlus", "AguaSegura", "RocaFuerte", "MetalCor",
    "ClimaFrost", "VentoMax",
]

# (razón social, primeros 8 dígitos del RNC — el 9.º se calcula)
PROVEEDORES = [
    ("Suministros Ferreteros del Cibao, S.R.L.", "10234567"),
    ("Distribuidora Antillana de Materiales, S.A.", "10345678"),
    ("Importadora Quisqueya, S.R.L.", "10456789"),
    ("Comercial Duarte Hermanos, S.A.", "10567890"),
    ("Ferretería Mayorista del Este, S.R.L.", "10678901"),
    ("Materiales y Construcción del Sur, S.A.", "10789012"),
    ("Distribuidora Eléctrica Nacional, S.R.L.", "10890123"),
    ("Grupo Ferretero Ozama, S.A.", "10901234"),
]

CLIENTES = [
    ("Constructora Vega y Asociados, S.R.L.", "10112233"),
    ("Remodelaciones Rodríguez, S.R.L.", "10223344"),
    ("Taller Mecánico El Progreso, S.R.L.", "10334455"),
    ("Inversiones Inmobiliarias del Caribe, S.A.", "10445566"),
    ("Constructora Los Tres Brazos, S.R.L.", "10556677"),
]

# (código, nombre, ícono, [(código_sub, nombre_sub, unidad, [(nombre, costo_min, costo_max), ...])])
CATEGORIAS = [
    ("CEM", "Cemento y Concreto", "catalogo", [
        ("CEM-SACO", "Cemento en saco", "SC", [
            ("Cemento gris tipo I 42.5 kg", 195, 230),
            ("Cemento gris tipo II 42.5 kg", 205, 240),
            ("Cemento blanco 42.5 kg", 320, 370),
            ("Cal hidratada 25 kg", 110, 130),
            ("Mortero premezclado 40 kg", 180, 210),
            ("Cemento para bloques 42.5 kg", 190, 220),
            ("Cemento de alta resistencia 42.5 kg", 260, 300),
        ]),
        ("CEM-AGRE", "Agregados", "QQ", [
            ("Arena lavada", 85, 100),
            ("Arena gruesa", 80, 95),
            ("Arena fina", 82, 97),
            ('Grava 3/4"', 90, 105),
            ('Gravilla 3/8"', 88, 103),
            ("Piedra picada", 95, 110),
        ]),
    ]),
    ("VAR", "Varillas y Acero", "camion", [
        ("VAR-COR", "Varillas corrugadas", "UD", [
            ('Varilla corrugada 3/8" x 20\'', 180, 210),
            ('Varilla corrugada 1/2" x 20\'', 290, 330),
            ('Varilla corrugada 5/8" x 20\'', 420, 470),
            ('Varilla corrugada 3/4" x 20\'', 590, 650),
            ('Varilla corrugada 1" x 20\'', 980, 1050),
            ('Varilla lisa 1/4" x 20\'', 95, 115),
            ('Varilla lisa 3/8" x 20\'', 170, 195),
            ('Varilla lisa 1/2" x 20\'', 275, 310),
        ]),
        ("VAR-MALLA", "Malla y alambre", "UD", [
            ("Malla electrosoldada 6x6 - 10/10", 850, 950),
            ("Malla electrosoldada 6x6 - 8/8", 1050, 1150),
            ("Malla ciclón galvanizada 6' x 50'", 3200, 3600),
            ("Alambre de amarre #16 (rollo)", 145, 170),
            ("Cabilla lisa 1/4\" x 20'", 90, 110),
        ]),
    ]),
    ("TOR", "Tornillería y Ferretería", "candado", [
        ("TOR-TOR", "Tornillos", "CJ", [
            ('Tornillo autorroscante 1" (caja 100u)', 210, 250),
            ('Tornillo autorroscante 1.5" (caja 100u)', 240, 280),
            ('Tornillo autorroscante 2" (caja 100u)', 270, 310),
            ('Tornillo drywall 1" (caja 500u)', 320, 370),
            ('Tornillo para madera 1.5" (caja 100u)', 190, 220),
            ('Tornillo para gypsum 1" (caja 500u)', 300, 350),
            ('Tornillo hexagonal 3/8" x 2" (caja 50u)', 410, 460),
            ('Tornillo de máquina 1/4" x 1" (caja 100u)', 230, 270),
        ]),
        ("TOR-TUE", "Tuercas y arandelas", "CJ", [
            ('Tuerca hexagonal 1/4" (caja 100u)', 120, 145),
            ('Tuerca hexagonal 3/8" (caja 100u)', 150, 180),
            ('Tuerca hexagonal 1/2" (caja 100u)', 210, 245),
            ('Arandela plana 3/8" (caja 100u)', 95, 115),
            ('Arandela plana 1/2" (caja 100u)', 110, 130),
            ('Arandela de presión 1/2" (caja 100u)', 105, 125),
            ('Perno de anclaje 1/2" x 4" (caja 25u)', 480, 540),
        ]),
        ("TOR-CLA", "Clavos", "CJ", [
            ('Clavo de acero 1.5" (caja 5 lb)', 160, 190),
            ('Clavo de acero 2" (caja 5 lb)', 175, 205),
            ('Clavo de acero 3" (caja 5 lb)', 195, 225),
            ('Clavo para concreto 1.5" (caja 1 lb)', 90, 110),
            ('Clavo galvanizado 3" (caja 5 lb)', 220, 255),
            ('Clavo con cabeza para techo 2.5" (caja 5 lb)', 260, 300),
            ('Grapa galvanizada 3/4" (caja 1 lb)', 75, 92),
        ]),
    ]),
    ("CAB", "Cables y Electricidad", "grafico", [
        ("CAB-ELEC", "Cable eléctrico", "RL", [
            ("Cable THHN #12 AWG (rollo 100m)", 2800, 3200),
            ("Cable THHN #10 AWG (rollo 100m)", 4200, 4800),
            ("Cable THHN #14 AWG (rollo 100m)", 2100, 2450),
            ("Cable THHN #8 AWG (rollo 100m)", 6500, 7200),
            ("Cable dúplex #12 (rollo 50m)", 1800, 2050),
            ("Cable concéntrico #8 (rollo 50m)", 3400, 3850),
            ("Cable UTP cat 6 (rollo 305m)", 5200, 5900),
        ]),
        ("CAB-ACC", "Accesorios eléctricos", "UD", [
            ("Breaker termomagnético 15A", 320, 370),
            ("Breaker termomagnético 20A", 330, 380),
            ("Breaker termomagnético 30A", 380, 440),
            ("Breaker termomagnético 40A", 420, 480),
            ("Tomacorriente doble polarizado", 85, 105),
            ("Interruptor sencillo", 65, 82),
            ("Caja octogonal galvanizada", 55, 70),
            ("Panel eléctrico 12 espacios", 1450, 1650),
            ("Regulador de voltaje 1000VA", 2200, 2500),
        ]),
    ]),
    ("TUB", "Tuberías y Plomería", "almacen", [
        ("TUB-PVC", "Tubería PVC", "UD", [
            ('Tubo PVC 1/2" x 10\' presión', 145, 170),
            ('Tubo PVC 3/4" x 10\' presión', 195, 225),
            ('Tubo PVC 1" x 10\' presión', 260, 300),
            ('Tubo PVC 4" x 10\' sanitario', 480, 550),
            ('Tubo PVC 6" x 10\' sanitario', 920, 1050),
            ('Tubo PVC 2" x 10\' sanitario', 310, 360),
            ('Tubo conduit PVC 1/2" x 10\'', 130, 155),
            ('Tubo conduit PVC 3/4" x 10\'', 165, 195),
        ]),
        ("TUB-ACC", "Accesorios de plomería", "UD", [
            ('Codo PVC 90° 1/2"', 22, 32),
            ('Codo PVC 90° 3/4"', 28, 38),
            ('Tee PVC 1/2"', 25, 35),
            ('Unión PVC 1/2"', 20, 28),
            ('Reducción PVC 3/4"x1/2"', 24, 33),
            ('Llave de paso 1/2"', 180, 210),
            ('Llave de paso 3/4"', 220, 255),
            ('Válvula check 3/4"', 260, 300),
            ('Adaptador macho PVC 1/2"', 18, 26),
        ]),
    ]),
    ("PIN", "Pinturas y Acabados", "catalogo", [
        ("PIN-LAT", "Pintura de látex", "GL", [
            ("Pintura látex blanco mate", 850, 980),
            ("Pintura látex color pastel", 920, 1050),
            ("Pintura látex exterior", 1050, 1200),
            ("Pintura látex para techos", 880, 1000),
            ("Sellador para pared", 650, 750),
            ("Primer sellador acrílico", 700, 800),
        ]),
        ("PIN-ACE", "Pintura de aceite", "GL", [
            ("Esmalte de aceite blanco", 980, 1120),
            ("Esmalte de aceite negro", 950, 1080),
            ("Esmalte de aceite gris", 960, 1090),
            ("Anticorrosivo rojo óxido", 780, 890),
            ("Barniz marino", 1100, 1250),
            ("Thinner (galón)", 380, 440),
        ]),
        ("PIN-ACC", "Accesorios de pintura", "UD", [
            ('Rodillo de pintura 9"', 145, 170),
            ('Brocha 3"', 95, 115),
            ("Bandeja para rodillo", 110, 130),
            ('Cinta de enmascarar 2"', 85, 100),
            ("Lija de agua #120", 25, 35),
            ('Espátula 4"', 90, 108),
        ]),
    ]),
    ("ELEC", "Línea Blanca y Electrodomésticos", "almacen", [
        ("ELEC-VEN", "Ventilación", "UD", [
            ('Abanico de pie 18" 3 velocidades', 1200, 1450),
            ('Abanico de pared 16"', 950, 1150),
            ('Abanico de techo 52" con luz', 2800, 3300),
            ("Abanico de torre oscilante", 1650, 1950),
            ("Extractor de aire para baño", 850, 1050),
        ]),
        ("ELEC-REF", "Refrigeración", "UD", [
            ("Nevera No Frost 14 pies cúbicos", 22000, 26000),
            ("Nevera No Frost 18 pies cúbicos", 28000, 33000),
            ("Freezer horizontal 7 pies cúbicos", 15500, 18500),
            ("Freezer vertical 10 pies cúbicos", 21000, 25000),
            ("Bebedero de agua fría y caliente", 6800, 8200),
        ]),
        ("ELEC-CLI", "Climatización", "UD", [
            ("Aire acondicionado Inverter 12,000 BTU", 24000, 28000),
            ("Aire acondicionado Inverter 18,000 BTU", 32000, 37000),
            ("Aire acondicionado de ventana 12,000 BTU", 18500, 21500),
            ("Deshumidificador 30 pintas", 9800, 11500),
        ]),
    ]),
    ("HER", "Herramientas", "camion", [
        ("HER-ELEC", "Herramientas eléctricas", "UD", [
            ('Taladro percutor 1/2"', 3800, 4300),
            ('Amoladora angular 4.5"', 2900, 3300),
            ('Sierra circular 7.25"', 4600, 5200),
            ("Rotomartillo SDS", 6200, 7000),
            ("Pulidora de piso", 8500, 9500),
            ("Caladora eléctrica", 3200, 3650),
            ("Compresor de aire 6 gal", 7800, 8800),
        ]),
        ("HER-MAN", "Herramientas manuales", "UD", [
            ("Martillo de uña 16 oz", 280, 330),
            ('Llave ajustable 10"', 320, 370),
            ("Cinta métrica 5m", 175, 205),
            ('Nivel de burbuja 24"', 450, 520),
            ("Juego de destornilladores (6 pzs)", 380, 440),
            ("Carretilla de construcción", 3400, 3850),
            ("Serrucho de mano", 290, 340),
            ('Alicate universal 8"', 260, 305),
            ("Tijera para lámina", 340, 390),
        ]),
    ]),
]

def _generar_rnc(base_8_digitos: str) -> str:
    """Calcula un RNC de 9 dígitos válido a partir de sus primeros 8, con el algoritmo de la DGII."""
    suma = sum(int(digito) * peso for digito, peso in zip(base_8_digitos, PESOS_RNC_9, strict=True))
    resto = suma % 11
    verificador = 11 - resto
    if verificador == 11:
        verificador = 2
    elif verificador == 10:
        verificador = 1
    return f"{base_8_digitos}{verificador}"


def _decimal(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES)


@dataclass
class LoteSimulado:
    """
    Un lote en memoria, con los mismos atributos que ``planificar_consumo``
    necesita leer (no hace falta que sea un ``Lote`` real para calcular el
    plan PEPS). ``lote_real`` se rellena después, cuando el ``Lote`` de
    verdad ya existe en la base y tiene ``pk``.
    """

    cantidad_disponible: Decimal
    costo_unitario: Decimal
    recibido_en: object
    lote_real: Lote | None = None


def _cantidad_tipica(costo: Decimal) -> tuple[int, int]:
    """Cantidad de entrada típica: mientras más barato el artículo, más volumen se compra de una vez."""
    base = float(costo)
    if base < 100:
        return (40, 150)
    if base < 500:
        return (20, 80)
    if base < 2000:
        return (10, 40)
    return (3, 15)


def _consumir(lotes: list[LoteSimulado], cantidad: Decimal) -> list:
    """
    Aplica sobre ``lotes`` (en memoria) el mismo algoritmo PEPS que usa la
    aplicación real, descontando de una vez la cantidad de cada lote
    consumido, y devuelve el plan resultante.
    """
    disponible = sum(lote.cantidad_disponible for lote in lotes)
    costo_promedio = (
        sum(lote.cantidad_disponible * lote.costo_unitario for lote in lotes) / disponible
    ).quantize(CUATRO_DECIMALES) if disponible else Decimal("0")
    ordenados = sorted(
        (lote for lote in lotes if lote.cantidad_disponible > 0), key=lambda lote: lote.recibido_en
    )
    plan = planificar_consumo(ordenados, cantidad, METODO_PEPS, costo_promedio)
    for item in plan:
        if item.lote is not None:
            item.lote.cantidad_disponible -= item.cantidad
    return plan


def _registrar_salida_simulada(eventos: list[dict], clave: tuple, almacen: Almacen, articulo_id: int,
                               fecha, cantidad: Decimal, plan: list, saldo: Decimal) -> None:
    """Agrega a ``eventos`` la salida ya resuelta por :func:`_consumir`."""
    costo_total = sum((item.costo_total for item in plan), Decimal("0")).quantize(CUATRO_DECIMALES)
    costo_unitario = (costo_total / cantidad).quantize(CUATRO_DECIMALES) if cantidad else Decimal("0")
    eventos.append({
        "tipo": "salida", "fecha": fecha, "clave": clave, "almacen": almacen,
        "articulo_id": articulo_id, "cantidad": cantidad, "costo_unitario": costo_unitario,
        "costo_total": costo_total, "saldo_posterior": saldo,
        "plan": [(item.lote, item.cantidad, item.costo_unitario) for item in plan],
    })


def _simular_articulo(articulo: Articulo, almacen: Almacen, eventos: list[dict], hace_seis_meses,
                      hoy, forzar_bajo_minimo: bool, forzar_en_cero: bool) -> list[LoteSimulado]:
    """
    Simula, en memoria, las compras y ventas de un artículo en un almacén a
    lo largo de seis meses, agregando un evento por cada una a la lista
    compartida ``eventos``. Devuelve los lotes resultantes, ya con su
    cantidad disponible final.
    """
    clave = (articulo.pk, almacen.pk)
    lotes: list[LoteSimulado] = []
    saldo = Decimal("0")
    ultima_fecha = hace_seis_meses

    num_entradas = random.randint(2, 5)
    minimo, maximo = _cantidad_tipica(articulo.costo_referencia)
    dias_disponibles = max((hoy - hace_seis_meses).days - 5, 1)
    fechas_entrada = sorted(
        hace_seis_meses + timedelta(days=random.randint(0, dias_disponibles)) for _ in range(num_entradas)
    )
    for indice, fecha in enumerate(fechas_entrada):
        deriva = Decimal("1") + indice * Decimal("0.04") + Decimal(str(round(random.uniform(-0.03, 0.03), 4)))
        costo = _decimal(articulo.costo_referencia * deriva)
        cantidad = _decimal(random.randint(minimo, maximo))
        saldo += cantidad
        ultima_fecha = fecha
        lote = LoteSimulado(cantidad_disponible=cantidad, costo_unitario=costo, recibido_en=fecha)
        lotes.append(lote)
        eventos.append({
            "tipo": "entrada", "fecha": fecha, "clave": clave, "almacen": almacen,
            "articulo_id": articulo.pk, "cantidad": cantidad, "costo_unitario": costo,
            "costo_total": (cantidad * costo).quantize(CUATRO_DECIMALES),
            "saldo_posterior": saldo, "lote_simulado": lote,
        })

    for _ in range(random.randint(2, 8)):
        disponible = sum(lote.cantidad_disponible for lote in lotes)
        if disponible <= 0:
            break
        ultima_fecha = min(ultima_fecha + timedelta(days=random.randint(1, 25)), hoy)
        tope = _decimal(random.randint(1, max(int(disponible * Decimal("0.4")), 1)))
        tope = min(tope, disponible)
        if tope <= 0:
            continue
        plan = _consumir(lotes, tope)
        saldo -= tope
        _registrar_salida_simulada(eventos, clave, almacen, articulo.pk, ultima_fecha, tope, plan, saldo)

    # Empujar deliberadamente por debajo del mínimo (o a cero) a los
    # artículos elegidos, para que el evaluador de alertas tenga algo que
    # encontrar apenas termine la siembra — el criterio §10.7 del brief.
    disponible = sum(lote.cantidad_disponible for lote in lotes)
    objetivo = None
    if forzar_en_cero and disponible > 0:
        objetivo = Decimal("0")
    elif forzar_bajo_minimo and disponible >= articulo.stock_minimo_defecto:
        objetivo = max(articulo.stock_minimo_defecto - 1, Decimal("0"))

    if objetivo is not None and disponible > objetivo:
        a_consumir = disponible - objetivo
        ultima_fecha = min(ultima_fecha + timedelta(days=random.randint(1, 10)), hoy)
        plan = _consumir(lotes, a_consumir)
        saldo -= a_consumir
        _registrar_salida_simulada(
            eventos, clave, almacen, articulo.pk, ultima_fecha, a_consumir, plan, saldo
        )

    return lotes


class Command(BaseCommand):
    """Siembra un catálogo, proveedores, clientes y seis meses de movimientos de demostración."""

    help = "Siembra datos de demostración: ferretería dominicana con inventario y movimientos realistas."

    def handle(self, *args, **opciones) -> None:
        random.seed(SEMILLA)
        self.stdout.write(self.style.MIGRATE_HEADING("Sembrando datos de demostración"))

        with transaction.atomic():
            almacenes = self._sembrar_almacenes()
            unidades = self._sembrar_unidades()
            marcas = self._sembrar_marcas()
            categorias_hoja = self._sembrar_categorias()
            proveedores = self._sembrar_proveedores()
            self._sembrar_clientes()
            articulos = self._sembrar_articulos(categorias_hoja, unidades, marcas, proveedores)

        with transaction.atomic():
            tipos = self._sembrar_tipos_movimiento()
            self._sembrar_movimientos_masivos(articulos, almacenes, tipos)

        usuario = Usuario.objects.filter(is_superuser=True).order_by("id").first()
        if usuario:
            self._sembrar_movimientos_vistosos(articulos, almacenes, tipos, usuario)

        self._sembrar_reglas_y_evaluar()

        self.stdout.write(self.style.SUCCESS(
            f"\nDemo sembrada: {len(articulos)} artículos, "
            f"{Movimiento.objects.count()} movimientos, {Lote.objects.count()} lotes."
        ))

    # -- Catálogo -------------------------------------------------------------
    def _sembrar_almacenes(self) -> list[Almacen]:
        datos = [
            ("ALM-01", "Almacén principal", "Av. Duarte 145, Santo Domingo"),
            ("ALM-02", "Sucursal Los Alcarrizos", "Carretera Duarte km 18, Los Alcarrizos"),
            ("ALM-03", "Sucursal Santiago", "Av. 27 de Febrero 88, Santiago de los Caballeros"),
        ]
        almacenes = []
        for codigo, nombre, direccion in datos:
            almacen, _ = Almacen.objects.get_or_create(
                codigo=codigo, defaults={"nombre": nombre, "direccion": direccion}
            )
            almacenes.append(almacen)
        self.stdout.write(f"  almacenes ................ {len(almacenes)}")
        return almacenes

    def _sembrar_unidades(self) -> dict[str, UnidadMedida]:
        unidades = {}
        for codigo, nombre, simbolo, decimales in UNIDADES:
            unidad, _ = UnidadMedida.objects.get_or_create(
                codigo=codigo,
                defaults={"nombre": nombre, "simbolo": simbolo, "permite_decimales": decimales},
            )
            unidades[codigo] = unidad
        self.stdout.write(f"  unidades de medida ....... {len(unidades)}")
        return unidades

    def _sembrar_marcas(self) -> list[Marca]:
        marcas = [Marca.objects.get_or_create(nombre=nombre)[0] for nombre in MARCAS]
        self.stdout.write(f"  marcas ................... {len(marcas)}")
        return marcas

    def _sembrar_categorias(self) -> list[tuple]:
        """Crea el árbol de categorías. Devuelve las hojas con su lista de productos."""
        hojas = []
        # Una sola lectura del árbol; cada categoría creada en este mismo
        # comando se agrega a la misma lista en memoria, así que las
        # búsquedas siguientes no vuelven a consultar la base.
        arbol = list(ServicioCategorias.arbol())
        for codigo, nombre, icono, subcategorias in CATEGORIAS:
            existente = next(
                (c for c in arbol if c.codigo == codigo and c.padre_id is None), None,
            )
            if existente:
                padre = existente
            else:
                padre = ServicioCategorias.crear(codigo, nombre, "", None, icono=icono)
                arbol.append(padre)
            for sub_codigo, sub_nombre, unidad_codigo, productos in subcategorias:
                sub_existente = next((c for c in arbol if c.codigo == sub_codigo), None)
                if sub_existente:
                    sub = sub_existente
                else:
                    sub = ServicioCategorias.crear(sub_codigo, sub_nombre, "", padre, icono=icono)
                    arbol.append(sub)
                hojas.append((sub, unidad_codigo, productos))
        total_productos = sum(len(productos) for _, _, productos in hojas)
        self.stdout.write(
            f"  categorías ................ {len(hojas)} hojas, {total_productos} plantillas de producto"
        )
        return hojas

    def _sembrar_proveedores(self) -> list[Proveedor]:
        proveedores = []
        for razon_social, base_rnc in PROVEEDORES:
            codigo = f"PROV{len(proveedores) + 1:03d}"
            existente = Proveedor.objects.filter(razon_social=razon_social).first()
            if existente:
                proveedores.append(existente)
                continue
            proveedor = ServicioProveedores.crear(
                codigo=codigo, razon_social=razon_social, rnc=_generar_rnc(base_rnc),
                telefono=f"809-{random.randint(200,999)}-{random.randint(1000,9999)}",
                dias_credito=random.choice([15, 30, 45, 60]),
            )
            proveedores.append(proveedor)
        self.stdout.write(f"  proveedores ............... {len(proveedores)}")
        return proveedores

    def _sembrar_clientes(self) -> None:
        creados = 0
        for razon_social, base_rnc in CLIENTES:
            if Cliente.objects.filter(razon_social=razon_social).exists():
                continue
            codigo = f"CLI{creados + 1:03d}"
            ServicioClientes.crear(
                codigo=codigo, razon_social=razon_social, rnc=_generar_rnc(base_rnc),
                telefono=f"809-{random.randint(200,999)}-{random.randint(1000,9999)}",
            )
            creados += 1
        self.stdout.write(f"  clientes .................. {creados}")

    def _sembrar_articulos(self, hojas, unidades, marcas, proveedores) -> list[Articulo]:
        articulos: list[Articulo] = []
        secuencias: dict[int, int] = {}
        minimos_por_unidad = {
            "SC": 20, "QQ": 15, "UD": 15, "CJ": 10, "GL": 8, "M": 50, "RL": 5, "PZ": 15, "KG": 25,
        }

        for categoria, unidad_codigo, productos in hojas:
            unidad = unidades[unidad_codigo]
            minimo = minimos_por_unidad.get(unidad_codigo, 10)
            for indice, (nombre, costo_min, costo_max) in enumerate(productos):
                variantes = [(nombre, False)]
                if indice % 3 == 0:
                    variantes.append((f"{nombre} (línea económica)", True))

                for nombre_variante, es_economica in variantes:
                    secuencias[categoria.pk] = secuencias.get(categoria.pk, 0) + 1
                    sku = f"{categoria.codigo}-{secuencias[categoria.pk]:05d}"
                    costo = Decimal(random.randint(costo_min, costo_max))
                    if es_economica:
                        costo = (costo * Decimal("0.8")).quantize(CUATRO_DECIMALES)
                    markup = Decimal(str(round(random.uniform(1.32, 1.6), 2)))
                    precio = (costo * markup).quantize(Decimal("0.01"))

                    articulo = Articulo(
                        sku=sku, nombre=nombre_variante, categoria=categoria,
                        marca=random.choice(marcas), unidad=unidad,
                        costo_referencia=costo, precio_venta=precio, tasa_itbis=Decimal("18"),
                        stock_minimo_defecto=Decimal(minimo), activo=True,
                    )
                    articulos.append(articulo)

        Articulo.objects.bulk_create(articulos)
        for categoria_id, ultima_secuencia in secuencias.items():
            Categoria.objects.filter(pk=categoria_id).update(secuencia_sku=ultima_secuencia)

        # Cada artículo queda ligado a uno o dos proveedores, con un precio de
        # compra cercano a su costo de referencia — así el catálogo tiene una
        # respuesta real cuando se pregunta «quién nos vende esto».
        relaciones = []
        for articulo in articulos:
            elegidos = random.sample(proveedores, k=random.choice([1, 1, 2]))
            for posicion, proveedor in enumerate(elegidos):
                variacion = Decimal(str(round(random.uniform(0.92, 1.05), 3)))
                relaciones.append(ProveedorArticulo(
                    proveedor=proveedor, articulo=articulo,
                    precio_compra=(articulo.costo_referencia * variacion).quantize(CUATRO_DECIMALES),
                    tiempo_entrega_dias=random.choice([2, 3, 5, 7, 10]),
                    cantidad_minima=Decimal(random.choice([1, 5, 10, 20])),
                    es_preferido=(posicion == 0),
                ))
        ProveedorArticulo.objects.bulk_create(relaciones)

        self.stdout.write(f"  artículos ................. {len(articulos)}")
        return articulos

    # -- Movimientos ------------------------------------------------------
    def _sembrar_tipos_movimiento(self) -> dict[str, TipoMovimiento]:
        datos = [
            ("COMPRA", "Compra", Naturaleza.ENTRADA, "ENT"),
            ("VENTA", "Venta", Naturaleza.SALIDA, "SAL"),
            ("TRASLADO", "Traslado entre almacenes", Naturaleza.TRANSFERENCIA, "TRF"),
            ("AJUSTE", "Ajuste de inventario", Naturaleza.AJUSTE, "AJU"),
        ]
        tipos = {}
        for codigo, nombre, naturaleza, prefijo in datos:
            tipo, _ = TipoMovimiento.objects.get_or_create(
                codigo=codigo,
                defaults={"nombre": nombre, "naturaleza": naturaleza, "prefijo_numeracion": prefijo},
            )
            tipos[codigo] = tipo
        return tipos

    def _sembrar_movimientos_masivos(self, articulos: list[Articulo], almacenes: list[Almacen],
                                     tipos: dict[str, TipoMovimiento]) -> None:
        """
        Simula seis meses de compras y ventas para cada artículo, resolviendo
        el consumo PEPS en memoria antes de escribir nada — así toda la
        aritmética se hace una sola vez, en Python, y la base solo recibe
        lotes de ``bulk_create`` ya correctos.
        """
        usuario = Usuario.objects.filter(is_superuser=True).order_by("id").first()
        if usuario is None:
            self.stdout.write(self.style.WARNING("  (sin administrador: se omiten los movimientos)"))
            return

        tipo_compra, tipo_venta = tipos["COMPRA"], tipos["VENTA"]
        hoy = timezone.now()
        hace_seis_meses = hoy - timedelta(days=180)

        # Cada evento es un diccionario con lo que hace falta para construir,
        # más adelante, el Movimiento/MovimientoLinea/Lote/ConsumoLote reales.
        eventos: list[dict] = []
        existencias: dict[tuple[int, int], dict] = {}
        pesos_almacenes = [0.6, 0.25, 0.15][: len(almacenes)]

        articulos_bajo_minimo = set(random.sample(articulos, k=min(10, len(articulos))))
        articulos_en_cero = set(
            random.sample(list(articulos_bajo_minimo), k=min(3, len(articulos_bajo_minimo)))
        )

        for articulo in articulos:
            almacen = random.choices(almacenes, weights=pesos_almacenes, k=1)[0]
            clave = (articulo.pk, almacen.pk)
            indice_inicial = len(eventos)
            lotes_sim = _simular_articulo(
                articulo, almacen, eventos, hace_seis_meses, hoy,
                forzar_bajo_minimo=articulo in articulos_bajo_minimo,
                forzar_en_cero=articulo in articulos_en_cero,
            )
            eventos_propios = eventos[indice_inicial:]
            cantidad_final = sum(lote.cantidad_disponible for lote in lotes_sim)
            valor_final = sum(lote.cantidad_disponible * lote.costo_unitario for lote in lotes_sim)
            ultimo = max((e["fecha"] for e in eventos_propios), default=None)
            existencias[clave] = {
                "articulo_id": articulo.pk, "almacen_id": almacen.pk,
                "cantidad": cantidad_final, "valor": valor_final,
                "stock_minimo": articulo.stock_minimo_defecto, "ultimo_movimiento_en": ultimo,
            }

        self._escribir_eventos(eventos, existencias, tipo_compra, tipo_venta, usuario)
        self.stdout.write(f"  movimientos (compra/venta) . {len(eventos)}")

    def _escribir_eventos(self, eventos: list[dict], existencias: dict, tipo_compra: TipoMovimiento,
                          tipo_venta: TipoMovimiento, usuario: Usuario) -> None:
        """Vuelca a la base, en etapas, lo que ``_simular_articulo`` calculó en memoria."""
        eventos.sort(key=lambda evento: evento["fecha"])

        secuencia_compra = tipo_compra.secuencia_actual
        secuencia_venta = tipo_venta.secuencia_actual
        movimientos = []
        for evento in eventos:
            if evento["tipo"] == "entrada":
                secuencia_compra += 1
                numero = f"{tipo_compra.prefijo_numeracion}-{secuencia_compra:06d}"
                tipo, naturaleza = tipo_compra, Naturaleza.ENTRADA
            else:
                secuencia_venta += 1
                numero = f"{tipo_venta.prefijo_numeracion}-{secuencia_venta:06d}"
                tipo, naturaleza = tipo_venta, Naturaleza.SALIDA

            movimiento = Movimiento(
                numero=numero, tipo=tipo, naturaleza=naturaleza, estado=EstadoMovimiento.CONFIRMADO,
                fecha=evento["fecha"], usuario=usuario, metodo_valoracion=METODO_PEPS,
                total_cantidad=evento["cantidad"], total_costo=evento["costo_total"],
                almacen_destino=evento["almacen"] if naturaleza == Naturaleza.ENTRADA else None,
                almacen_origen=evento["almacen"] if naturaleza == Naturaleza.SALIDA else None,
            )
            evento["movimiento"] = movimiento
            movimientos.append(movimiento)
        Movimiento.objects.bulk_create(movimientos, batch_size=500)
        TipoMovimiento.objects.filter(pk=tipo_compra.pk).update(secuencia_actual=secuencia_compra)
        TipoMovimiento.objects.filter(pk=tipo_venta.pk).update(secuencia_actual=secuencia_venta)

        lineas = []
        for evento in eventos:
            linea = MovimientoLinea(
                movimiento=evento["movimiento"], articulo_id=evento["articulo_id"],
                almacen_id=evento["almacen"].pk, signo=(1 if evento["tipo"] == "entrada" else -1),
                cantidad=evento["cantidad"], costo_unitario=evento["costo_unitario"],
                costo_total=evento["costo_total"], saldo_posterior=evento["saldo_posterior"],
            )
            evento["linea"] = linea
            lineas.append(linea)
        MovimientoLinea.objects.bulk_create(lineas, batch_size=500)

        lotes_nuevos = []
        for evento in eventos:
            if evento["tipo"] != "entrada":
                continue
            lote = Lote(
                codigo=evento["movimiento"].numero, articulo_id=evento["articulo_id"],
                almacen_id=evento["almacen"].pk, linea_origen=evento["linea"],
                costo_unitario=evento["costo_unitario"], cantidad_inicial=evento["cantidad"],
                cantidad_disponible=evento["cantidad"], recibido_en=evento["fecha"],
            )
            evento["lote_simulado"].lote_real = lote
            lotes_nuevos.append(lote)
        Lote.objects.bulk_create(lotes_nuevos, batch_size=500)

        consumos = []
        for evento in eventos:
            if evento["tipo"] != "salida":
                continue
            for lote_simulado, cantidad, costo_unitario in evento["plan"]:
                consumos.append(ConsumoLote(
                    linea=evento["linea"], lote=lote_simulado.lote_real if lote_simulado else None,
                    cantidad=cantidad, costo_unitario=costo_unitario,
                ))
        ConsumoLote.objects.bulk_create(consumos, batch_size=500)

        # Los lotes quedan con la cantidad ya consumida por las salidas simuladas.
        lotes_a_actualizar = []
        for evento in eventos:
            if evento["tipo"] == "entrada":
                simulado = evento["lote_simulado"]
                if simulado.lote_real.cantidad_disponible != simulado.cantidad_disponible:
                    simulado.lote_real.cantidad_disponible = simulado.cantidad_disponible
                    lotes_a_actualizar.append(simulado.lote_real)
        Lote.objects.bulk_update(lotes_a_actualizar, ["cantidad_disponible"], batch_size=500)

        for datos in existencias.values():
            Existencia.objects.update_or_create(
                articulo_id=datos["articulo_id"], almacen_id=datos["almacen_id"],
                defaults={
                    "cantidad": datos["cantidad"], "valor": datos["valor"],
                    "stock_minimo": datos["stock_minimo"],
                    "ultimo_movimiento_en": datos["ultimo_movimiento_en"],
                },
            )

    def _sembrar_movimientos_vistosos(self, articulos: list[Articulo], almacenes: list[Almacen],
                                      tipos: dict[str, TipoMovimiento], usuario: Usuario) -> None:
        """
        Un puñado de movimientos bien recientes, registrados con el servicio
        real — para que el recorrido de aceptación tenga algo fresco que
        mirar y para ejercitar transferencias y ajustes, que la siembra
        masiva no simula. Cada uno se intenta por separado: que uno falle
        (un artículo sin existencia suficiente, por ejemplo) no debe tumbar
        a los demás ni al resto de la siembra.
        """
        proveedor = Proveedor.objects.first()
        articulo_para_entrada = random.choice(articulos)
        try:
            ServicioMovimientos.registrar_entrada(
                tipo=tipos["COMPRA"], almacen_destino=almacenes[0], usuario=usuario,
                lineas=[{
                    "articulo_id": articulo_para_entrada.pk, "cantidad": Decimal("40"),
                    "costo_unitario": articulo_para_entrada.costo_referencia,
                }],
                proveedor=proveedor, documento_tipo="Factura",
                documento_numero="F-00512", motivo="Reposición de inventario",
            )
        except ValidationError as error:
            self.stdout.write(self.style.WARNING(f"  (entrada de muestra omitida: {error})"))

        # Para la salida, la transferencia y el ajuste hace falta existencia
        # real en el almacén de origen — se eligen entre los artículos que sí
        # la tienen, no al azar sobre todo el catálogo.
        bien_surtidos = list(
            Existencia.objects.filter(almacen=almacenes[0], cantidad__gte=15)
            .select_related("articulo").order_by("?")[:3]
        )

        if bien_surtidos:
            existencia = bien_surtidos[0]
            try:
                ServicioMovimientos.registrar_salida(
                    tipo=tipos["VENTA"], almacen_origen=almacenes[0], usuario=usuario,
                    lineas=[{"articulo_id": existencia.articulo_id, "cantidad": Decimal("5")}],
                    documento_tipo="Factura", documento_numero="F-00513",
                )
            except ValidationError as error:
                self.stdout.write(self.style.WARNING(f"  (salida de muestra omitida: {error})"))

        if len(bien_surtidos) > 1 and len(almacenes) > 1:
            existencia = bien_surtidos[1]
            try:
                ServicioMovimientos.registrar_transferencia(
                    tipo=tipos["TRASLADO"], almacen_origen=almacenes[0], almacen_destino=almacenes[1],
                    usuario=usuario, motivo="Balanceo de existencia entre sucursales",
                    lineas=[{"articulo_id": existencia.articulo_id, "cantidad": Decimal("8")}],
                )
            except ValidationError as error:
                self.stdout.write(self.style.WARNING(f"  (transferencia de muestra omitida: {error})"))

        if len(bien_surtidos) > 2:
            existencia = bien_surtidos[2]
            try:
                ServicioMovimientos.registrar_ajuste(
                    tipo=tipos["AJUSTE"], almacen=almacenes[0], usuario=usuario,
                    motivo="Conteo físico mensual — sobrante encontrado en anaquel",
                    lineas=[{"articulo_id": existencia.articulo_id, "cantidad": Decimal("2"), "signo": 1}],
                )
            except ValidationError as error:
                self.stdout.write(self.style.WARNING(f"  (ajuste de muestra omitido: {error})"))

        self.stdout.write("  movimientos de muestra ..... vía ServicioMovimientos")

    def _sembrar_reglas_y_evaluar(self) -> None:
        ReglaAlerta.objects.get_or_create(
            nombre="Existencia por debajo del mínimo", defaults={"tipo": TipoRegla.STOCK_BAJO},
        )
        ReglaAlerta.objects.get_or_create(
            nombre="Existencia en cero", defaults={"tipo": TipoRegla.STOCK_CERO},
        )
        ReglaAlerta.objects.get_or_create(
            nombre="Noventa días sin movimiento",
            defaults={"tipo": TipoRegla.SIN_MOVIMIENTO, "dias_umbral": 90},
        )
        evaluadas = ServicioEvaluador.evaluar_todo()
        total_alertas = Alerta.objects.count()
        self.stdout.write(f"  reglas evaluadas .......... {evaluadas} ({total_alertas} alertas)")
