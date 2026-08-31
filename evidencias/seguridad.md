# Verificación de los once puntos de seguridad — cierre de Fase 8

Los once puntos del §6 del brief base se revisaron uno por uno contra el
estado actual del código, después de las ocho fases de este brief. Todos
siguen aplicando y siguen comentados donde viven.

| # | Punto | Dónde vive | Estado |
|---|---|---|---|
| 1 | Hash de contraseñas con Argon2 | `config/settings/base.py:119`, `apps/nucleo/services.py:195` | Vigente |
| 2 | CSRF activo en todos los formularios, incluidos los de HTMX | `plantillas/base.html:34` (`hx-headers` con el token), `estaticos/js/kardex.js:9-16` (lo agrega a cada petición HTMX que no sea GET) | Vigente |
| 3 | Solo ORM; prohibido `raw()` o SQL concatenado | Verificado con `grep -rn "\.raw(\|cursor\.execute"` sobre `apps/*/services.py`, `apps/*/repositories.py`, `apps/*/views.py` — cero resultados en toda la app, incluidos los tres módulos nuevos (catálogo, movimientos, alertas) | Vigente |
| 4 | Permisos verificados en el servidor con decorador, 403 ante una URL directa sin permiso | `apps/nucleo/decoradores.py` (`@requiere_permiso`), aplicado en las cinco apps; probado en `test_permisos.py` y en el `test_*_exige_permiso` de cada app nueva | Vigente |
| 5 | Secretos por variable de entorno, `.env` en `.gitignore` | `config/settings/base.py:31`, `.gitignore` línea `.env` | Vigente |
| 6 | `DEBUG=False`, `ALLOWED_HOSTS` cerrado, HTTPS y cookies seguras en producción | `config/settings/produccion.py:27` | Vigente |
| 7 | django-axes: 5 intentos, bloqueo de 30 minutos | `config/settings/base.py:137`, `apps/nucleo/views.py:112` | Vigente |
| 8 | Auditoría inmutable con IP y usuario | `apps/nucleo/models.py:217` (`RegistroAuditoria`), extendida esta sesión a los movimientos (`Movimiento.save()`/`.delete()`) y ahora también a `MovimientoLinea`, siguiendo el mismo patrón | Vigente y ampliada |
| 9 | Validación en cliente y servidor, la del servidor manda | `apps/configuracion/forms.py:106`, `apps/nucleo/forms.py:7`; los formularios nuevos de movimientos y catálogo repiten el patrón (validación de formulario + `ValidationError` de servicio) | Vigente |
| 10 | `pip-audit` en `requirements-dev.txt` y Dependabot activo | `requirements-dev.txt` ya lo tenía; **faltaba el archivo de Dependabot** — se agregó `.github/dependabot.yml` en esta fase (no existía ningún registro de que se hubiera activado antes) | Corregido esta fase |
| 11 | Subida de archivos: extensión, tamaño y nombre saneados en servidor | `apps/nucleo/utilidades.py` (`validar_archivo_subido`, `sanear_nombre_archivo`); esta sesión se le sumó `sanear_celda_hoja_de_calculo` para la inyección de fórmulas en Excel/CSV, la misma familia de riesgo (entrada del usuario que termina en un archivo que otro programa interpreta) | Vigente y ampliada |

## Hallazgo nuevo de esta fase (no en la lista original, pero de la misma familia)

Durante `/code-review` se encontró que los reportes Excel y el CSV de errores
de importación escribían texto libre del usuario (nombre de artículo) sin
neutralizar un posible inicio de fórmula (`=`, `+`, `-`, `@`) — inyección de
fórmulas de hoja de cálculo (CWE-1236), la misma clase de problema que el
punto 11 ya cubre para la subida de archivos. Se corrigió con
`sanear_celda_hoja_de_calculo()` en `apps/nucleo/utilidades.py`, aplicada en
`apps/alertas/reportes/excel.py` y `apps/catalogo/importacion.py`, con
prueba dedicada en `pruebas/test_semilla_y_utilidades.py`.

## Conclusión

Los once puntos originales siguen vigentes. Uno de ellos (Dependabot) estaba
incompleto y se corrigió. Dos de ellos (auditoría inmutable y saneamiento de
entrada del usuario) se ampliaron para cubrir el código nuevo de esta sesión.
