# Auditoría de botones muertos — Fase 7

Recorrido completo de la interfaz contra los diez puntos del §8 del brief.
Regla que gobierna todo lo demás: **si una función no está construida, el
botón no existe.**

## 1. Botones sin función (`type="button"` sin acción)

Script estático que recorre cada plantilla bajo `plantillas/`, extrae cada
etiqueta `<button ... type="button" ...>` y la marca como sospechosa si no
tiene ninguno de los atributos que disparan una acción real (`hx-get`,
`hx-post`, `hx-boost`, `data-cerrar-modal`, `data-formset-agregar`,
`data-formset-quitar`, `onclick`, `@click`, `type="submit"`, `form=`, etc.).

Resultado: **un solo caso marcado**, sobre el centenar de plantillas del
proyecto:

```
plantillas\base.html:70  <button class="boton-menu" type="button" aria-label="Abrir el menú">
```

Es el botón de hamburguesa del menú lateral en móvil. No lleva atributo
inline porque su manejador está delegado por clase en
`estaticos/js/kardex.js`:

```js
document.addEventListener("click", function (evento) {
  if (evento.target.closest(".boton-menu")) abrirLateral();
  ...
});
```

El script de detección solo entiende atributos inline, no delegación por
clase — **falso positivo confirmado por lectura directa de `kardex.js`**, no
es un botón muerto. No se encontró ningún botón realmente sin función.

## 2. Enlaces a ancla vacía (`href="#"`)

`grep -rn 'href="#"' plantillas/` → **cero coincidencias**.

## 3. Texto "próximamente" o de andamiaje

`grep -rn 'próximamente\|todavía no está construido\|andamio' plantillas/ apps/`
encontró un solo resto: `apps/movimientos/plantillas/movimientos/indice.html`,
una plantilla de la era de andamiaje. Ya estaba **inerte** — Django resuelve
plantillas desde `DIRECTORIOS_PLANTILLAS = [BASE_DIR/"plantillas"] + apps`,
así que la plantilla real en `plantillas/movimientos/indice.html` la tapaba
siempre — pero seguía en el repositorio, así que se **eliminó**, junto con
`plantillas/componentes/encabezado_pagina.html` (quedó huérfano, solo esa
plantilla lo usaba) y cuatro directorios `plantillas/` vacíos que quedaron
bajo `apps/configuracion/` y `apps/nucleo/`. Tras la limpieza: cero
coincidencias.

## 4. Cada entrada de menú resuelve a una pantalla real

Las 16 entradas declaradas en los cinco `apps/*/navegacion.py` se resolvieron
con `django.urls.reverse()`: **16 de 16 responden**, ninguna URL rota.

| Título | Ruta | Permiso |
|---|---|---|
| Panel | `nucleo:panel` | — |
| Catálogo | `catalogo:articulos` | `articulo.ver` |
| Movimientos | `movimientos:indice` | `movimiento.ver` |
| Existencias | `movimientos:existencias` | `movimiento.ver` |
| Aprobaciones | `movimientos:aprobaciones` | `movimiento.aprobar` |
| Tipos de movimiento | `movimientos:tipos` | `tipo_movimiento.gestionar` |
| Alertas | `alertas:indice` | `alerta.ver` |
| Reglas de alerta | `alertas:reglas` | `alerta.configurar` |
| Reportes | `alertas:reportes_indice` | `reporte.ver` |
| Almacenes | `nucleo:almacenes` | `almacen.gestionar` |
| Usuarios | `nucleo:usuarios` | `usuario.gestionar` |
| Roles y permisos | `nucleo:roles` | `usuario.gestionar` |
| Auditoría | `nucleo:auditoria` | `reporte.ver` |
| Parámetros | `configuracion:parametros` | `configuracion.gestionar` |
| Campos personalizados | `configuracion:campos` | `configuracion.gestionar` |
| Etiquetas | `configuracion:etiquetas` | `configuracion.gestionar` |

## 5. Cada formulario guarda y confirma

Los flujos de movimientos (entrada, salida, transferencia, ajuste,
aprobación, rechazo, anulación), alertas (reglas, resolución), importación
masiva de artículos y catálogo (artículo, categoría con campo personalizado,
marca, proveedor, cliente) se probaron en vivo con el navegador durante las
Fases 3 a 5: cada guardado exitoso cierra el modal y muestra un aviso
(`respuesta_exito`) o redirige. Las pantallas heredadas de la Fase 2
(usuarios, roles, almacenes, parámetros, campos, etiquetas) ya se habían
verificado en su propia fase. Revisión adicional: cada rama `is_valid()` de
cada vista de formulario termina en `respuesta_exito`/`respuesta_aviso` o un
redirect — ninguna vuelve a renderizar el formulario en silencio tras un
guardado correcto.

## 6. Cada filtro filtra de verdad

Patrón uniforme: cada pantalla de listado lee sus parámetros de
`request.GET`, los aplica al `QuerySet` del repositorio/servicio, y arma
`fichas_de_filtro()` para mostrar lo que está activo. Verificado por
inspección de las 9 vistas de listado — todas pasan sus parámetros de
búsqueda/estado/almacén/categoría al `QuerySet` antes de `paginar()`.

## 7. Cada exportación descarga un archivo válido

PDF y Excel de existencias, kardex y los cuatro reportes de `alertas`, y el
CSV de errores de la importación masiva, se verificaron en vivo durante la
Fase 5 (descarga real, apertura del archivo, contenido correcto con
membrete, filtros aplicados y pie "Página X de Y" en los PDF).

## 8. Cada eliminación confirma y explica la consecuencia

Se auditaron los ocho puntos donde el texto de la plantilla dice "Eliminar",
"Anular", "Rechazar", "Desactivar" o "Inactivar":

| Acción | Mecanismo | Explica la consecuencia |
|---|---|---|
| Eliminar categoría | `hx-confirm` | «Solo se puede si no tiene subcategorías ni artículos» |
| Eliminar rol | `hx-confirm` | «Esta acción no se puede deshacer» |
| Aprobar movimiento | `hx-confirm` | «Se aplicará sobre el inventario de inmediato» |
| Anular movimiento | modal con motivo obligatorio | «Se creará un movimiento contrapartida... El original no se borra ni se edita» |
| Rechazar movimiento (pendiente) | modal con motivo obligatorio | «Quedará marcado como rechazado, sin ningún efecto sobre el inventario» |
| Desactivar cliente/proveedor/etiqueta | alternador reversible | acción no destructiva (baja lógica, reversible con "Activar") |

Las eliminaciones y anulaciones —las únicas acciones realmente
irreversibles o de efecto inmediato sobre el inventario— piden confirmación
explícita con el texto de la consecuencia. Los alternadores de
activo/inactivo no la piden porque son reversibles con un segundo clic, no
son un borrado.

## 9. Cada tabla ordena por las columnas que ofrece

Se cruzaron las 21 declaraciones de columna con `"clave"` (la que activa el
enlace de orden en `componentes/tabla.html`) contra las llamadas a
`ordenar()` de cada vista, en las cuatro apps que tienen listados.

**Se encontraron y corrigieron dos casos reales** donde la tabla ofrecía
ordenar por una columna, pero la vista nunca llamaba a `ordenar()` — el
enlace cambiaba la URL sin cambiar el orden mostrado:

- `apps/catalogo/views.py::marcas` — columna «Marca» (clave `nombre`)
- `apps/catalogo/views.py::unidades` — columnas «Código» y «Nombre»

Corregido añadiendo `PERMITIDAS_MARCA`/`PERMITIDAS_UNIDAD` y la llamada a
`ordenar()` antes de `paginar()` en ambas vistas. El resto de columnas con
`clave` (artículos, proveedores, clientes, etiquetas, movimientos,
almacenes, usuarios, roles, auditoría) ya estaban correctamente conectadas.
Las tablas sin columnas `clave` (alertas, existencias, kardex, campos
personalizados) no ofrecen enlaces de orden que no cumplan — el orden no
tiene sentido en esas pantallas (kardex es cronológico, campos usa
arrastre manual) y sus plantillas no los muestran.

## 10. Cada paginación pagina de verdad

`paginar()` usa el `Paginator` real de Django sobre `filas_por_pagina` (o el
tamaño explícito de la vista), respeta `?pagina=`, cae a la página 1 ante un
número inválido o vacío, y conserva el resto de parámetros de filtro al
saltar de página. Las 15 vistas de listado que devuelven resultados
paginables la usan.

## Conclusión

Un botón muerto encontrado por el barrido automático, verificado como falso
positivo (delegación por clase en JavaScript). Dos enlaces de orden de
columna que no ordenaban, corregidos. Un resto de plantilla de andamiaje
inerte, eliminado junto con su huérfano. Cero anclas vacías, cero texto
"próximamente", cero rutas de menú rotas, cero eliminaciones sin
confirmación explicando la consecuencia.
