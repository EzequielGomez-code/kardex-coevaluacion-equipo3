"""
Servicios de Movimientos — los construye Cristian.

Aquí van las reglas de negocio. Un servicio llama a repositorios, nunca al ORM
directamente, y devuelve objetos de dominio o lanza ``ValidationError``.

Lo que la base ya deja resuelto y conviene reutilizar::

    from apps.nucleo.services import ServicioAuditoria
    from apps.configuracion.services import (
        ServicioCamposPersonalizados,
        ServicioParametros,
    )

    # Un parámetro editable desde pantalla, sin tocar el código:
    if not ServicioParametros.obtener("permitir_stock_negativo", False):
        ...

    # Campos que el usuario agregó por su cuenta:
    ServicioCamposPersonalizados.guardar_valores(articulo, request.POST)

    # Rastro inmutable de la acción:
    ServicioAuditoria.registrar(entidad="Articulo", entidad_id=articulo.pk,
                                accion="crear", detalle={"sku": articulo.sku})
"""

# TODO(Cristian): agregar los servicios de esta app.
