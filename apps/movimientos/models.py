"""
Modelos de Movimientos — los construye Cristian.

Alcance de esta app: entradas, salidas, transferencias y el kardex valorado.
Entidades previstas: Movimiento, TipoMovimiento, LineaMovimiento.

Pautas que hereda de la base, para no romper lo que ya está montado:

* Nombres de dominio en español; palabras clave de Django en inglés.
* Heredar de ``apps.nucleo.models.ModeloConMarcaDeTiempo`` para tener
  ``creado_en`` y ``actualizado_en`` sin repetirlos.
* Los campos que el usuario deba poder agregar por su cuenta NO se declaran
  aquí: se definen desde la pantalla de campos personalizados y se leen con
  ``ServicioCamposPersonalizados.campos_de("Movimiento")``.
* Toda acción que cambie datos debe dejar su registro con
  ``ServicioAuditoria.registrar(...)`` desde el servicio, nunca desde la vista.
"""

# pylint: disable=unused-import
from django.db import models  # noqa: F401  (andamio: se usará al declarar los modelos)  (lo usará Cristian)

# TODO(Cristian): declarar aquí Movimiento, TipoMovimiento, LineaMovimiento.
