# Evidencia del despliegue

| Dato | Valor |
|---|---|
| URL pública | https://kardex-aco4.onrender.com |
| Repositorio | https://github.com/EzequielGomez-code/kardex (privado) |
| Servicio Render | `kardex` · plan Free · región Oregon · `srv-da9qscijnfac73elc0fg` |
| Base de datos | Neon PostgreSQL 18.6 · `ep-twilight-mountain-a569l2kz` · us-east-2 |
| Commit desplegado | `44ed1c9` |
| Despliegue automático | activado en cada `push` a `main` |

## Comprobaciones hechas contra la URL pública

- La pantalla de acceso responde HTTP 200 sobre HTTPS.
- Se entra con el usuario `admin` y se ve el panel con la barra lateral completa.
- El panel lee de Neon: 2 almacenes, 1 usuario y 6 roles sembrados.
- El inicio de sesión quedó registrado en la auditoría, con fecha y hora en la
  zona `America/Santo_Domingo`.
- El pie muestra la versión y el commit corto (`44ed1c9`).
- Los estáticos los sirve WhiteNoise con nombre versionado por hash y
  compresión brotli, sin S3 ni CDN.

## Nota sobre la primera carga

Render duerme el servicio a los 15 minutos de inactividad. La primera petición
después de un rato tarda entre 30 y 60 segundos mientras despierta la instancia.
Durante ese arranque el navegador puede alcanzar a cachear una respuesta
incompleta de un archivo estático; como WhiteNoise los marca `immutable`, esa
copia mala se queda pegada. Se resuelve con una recarga forzada (Ctrl+F5).
