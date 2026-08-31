# BRIEF 01 — Base del proyecto Kardex
**Para: el asistente de código · Ejecuta: Ezequiel Gómez Cepeda · Rama: `main`**

Pega este archivo completo en el asistente de código y dile: *"Construye esto. Empieza por el punto 1 y no pases al siguiente hasta que el anterior corra."*

---

## 1. Qué se va a construir

**Kardex** — sistema web de gestión de inventario multi-almacén, altamente configurable, para la Ferretería M y F, S.R.L. Es el proyecto de la asignatura INF-5250 del Equipo #3 de la UASD.

La idea rectora: **el usuario configura el sistema desde la interfaz, no desde el código.** Categorías, campos, tipos de movimiento, reglas de alerta, roles, permisos y vistas se definen en pantalla. Agregar un tipo de negocio nuevo no debe requerir un despliegue.

Este brief construye **solo la base**. Los tres módulos funcionales los construyen otros integrantes sobre esta base, cada uno en su propia rama.

---

## 2. Stack — no negociable

| Capa | Tecnología | Nota |
|---|---|---|
| Lenguaje | Python 3.12 | |
| Framework | Django 5.x | Trae auth, permisos, ORM, migraciones y panel de administración |
| Base de datos | PostgreSQL (Neon en la nube) · SQLite en local | Un solo `DATABASE_URL` decide cuál |
| Interactividad | HTMX 2.x + Alpine.js | Sin build de npm, sin React, sin `node_modules` |
| Estilos | CSS propio con variables | Sin Tailwind, sin Bootstrap |
| Estáticos | WhiteNoise | Sirve estáticos desde el propio Django, sin S3 |
| Formularios | django-crispy-forms | Solo si simplifica; si no, formularios a mano |
| Config | django-environ | Todo secreto sale de variables de entorno |
| Pruebas | pytest-django + coverage | |
| Análisis estático | Pylint + Ruff | El `.pylintrc` se crea en este brief |

**Prohibido:** cualquier dependencia de npm, cualquier framework de CSS, cualquier servicio de pago, cualquier credencial escrita en el código.

---

## 3. Estructura de carpetas

```
kardex/
├── config/                    proyecto Django (settings, urls, wsgi, asgi)
│   └── settings/
│       ├── base.py
│       ├── local.py
│       └── produccion.py
├── apps/
│   ├── nucleo/                usuarios, roles, permisos, almacenes, auditoría
│   ├── configuracion/         campos personalizados, parámetros, vistas guardadas
│   ├── catalogo/             (vacío, lo llena Arturo)
│   ├── movimientos/          (vacío, lo llena Cristian)
│   └── alertas/              (vacío, lo llena Francisco)
├── plantillas/
│   ├── base.html              layout maestro
│   ├── componentes/           tabla, filtros, modal, badge, paginación, toast
│   └── nucleo/
├── estaticos/
│   ├── css/
│   │   ├── tokens.css
│   │   ├── base.css
│   │   └── componentes.css
│   └── js/
│       └── kardex.js          menos de 150 líneas
├── pruebas/
├── docs/
│   └── briefs/
├── .pylintrc
├── .env.ejemplo
├── .gitignore
├── requirements.txt
├── build.sh
├── render.yaml
└── README.md
```

Las tres apps vacías se crean **con su estructura completa** (`models.py`, `views.py`, `urls.py`, `services.py`, `repositories.py`, `admin.py`, carpeta de plantillas y de pruebas) pero sin lógica. Así los compañeros llegan y solo llenan.

**Regla de capas, sin excepciones:** una vista llama a un servicio, un servicio llama a un repositorio, un repositorio toca la base. Ninguna vista hace `Model.objects.filter(...)` directamente. Ningún repositorio contiene reglas de negocio.

---

## 4. Modelos de esta base

### 4.1 App `nucleo`

```
Rol            id, nombre, descripcion, es_sistema
Permiso        id, clave, descripcion, modulo
RolPermiso     rol, permiso
Usuario        (hereda AbstractUser) rol, nombre_completo, telefono, activo
Almacen        id, codigo, nombre, direccion, encargado, activo
RegistroAuditoria  usuario, entidad, entidad_id, accion, detalle(JSON), ip, creado_en
```

`RegistroAuditoria` es inmutable: sobrescribe `save()` para rechazar actualizaciones y `delete()` para lanzar excepción.

Permisos iniciales por clave, cargados en un fixture: `articulo.ver`, `articulo.crear`, `articulo.editar`, `articulo.eliminar`, `movimiento.ver`, `movimiento.crear`, `movimiento.anular`, `movimiento.aprobar`, `almacen.gestionar`, `usuario.gestionar`, `configuracion.gestionar`, `reporte.ver`, `alerta.ver`, `alerta.resolver`.

Roles iniciales en fixture, con los permisos que corresponden a los seis actores de la SRS: Administrador de TI, Gerente de almacén, Operador de almacén, Gerente de compras, Gerente de ventas, Auditor.

### 4.2 App `configuracion` — la capa que hace el sistema personalizable

Esta app es el corazón de lo que pide el proyecto. Cada tabla convierte una decisión de negocio en datos editables desde la interfaz.

```
Parametro           clave, valor, tipo, etiqueta, grupo, editable
                    Ej: moneda=RD$, formato_sku, permitir_stock_negativo,
                    metodo_valoracion=PEPS, dias_sin_movimiento, zona_horaria

DefinicionCampo     entidad, categoria(opcional), clave, etiqueta, tipo,
                    requerido, orden, opciones(JSON), ayuda, activo
                    tipo: texto | numero | decimal | fecha | booleano |
                          lista | lista_multiple | usuario | archivo

ValorCampo          definicion, objeto_id, valor_texto, valor_numero,
                    valor_fecha, valor_bool

Etiqueta            nombre, color, activo
EtiquetaObjeto      etiqueta, entidad, objeto_id

VistaGuardada       usuario, nombre, entidad, filtros(JSON),
                    columnas(JSON), orden, compartida, por_defecto

FlujoAprobacion     nombre, entidad, condicion(JSON), rol_aprobador,
                    orden, activo

PlantillaNotificacion  clave, asunto, cuerpo, canal, variables(JSON), activa

MapeoImportacion    nombre, entidad, mapeo_columnas(JSON), usuario, creado_en
```

**`DefinicionCampo` + `ValorCampo` son genéricos**: usan `entidad` (texto) + `objeto_id` para colgarse de cualquier modelo. Esto permite que Arturo agregue campos personalizados a productos, Cristian a movimientos y Francisco a proveedores, sin que ninguno tenga que tocar esta app.

Entrega en esta app:
- Un servicio `ServicioCamposPersonalizados` con `campos_de(entidad, categoria)`, `valores_de(objeto)`, `guardar_valores(objeto, datos)` y `validar(entidad, datos)`.
- Un formulario dinámico de Django que arma los widgets a partir de las `DefinicionCampo` activas.
- Una pantalla de administración donde se crean y ordenan los campos, con arrastre para reordenar (Alpine.js).
- Una pantalla de "Parámetros del sistema" agrupada por secciones.

### 4.3 Migraciones y datos semilla

Un comando `python manage.py sembrar` que carga: permisos, roles, un usuario administrador, dos almacenes de ejemplo, los parámetros por defecto y tres definiciones de campo de muestra. Idempotente: se puede correr dos veces sin duplicar.

---

## 5. Interfaz

### 5.1 Estructura de pantalla

Barra lateral fija de 220 px con el menú por módulos. Barra superior de 48 px con migas de pan, buscador global y menú de usuario. Contenido a ancho completo, sin columna centrada.

El menú lateral se arma desde `apps/*/navegacion.py`: cada app declara sus entradas con su clave de permiso, y el layout las recoge. Así los compañeros agregan su sección sin editar el `base.html`.

### 5.2 Tokens de diseño (`estaticos/css/tokens.css`)

```css
:root {
  --fondo:          #F5F4F0;
  --superficie:     #FFFFFF;
  --superficie-alt: #FAF9F6;
  --borde:          #DCD9D1;
  --borde-fuerte:   #C2BEB4;

  --texto:   #23211E;
  --texto-2: #6A665F;
  --texto-3: #918C83;

  --acento:       #1F5B4E;
  --acento-hover: #17463C;
  --acento-suave: #E7EFEC;

  --alerta: #A03A22;
  --aviso:  #8A6410;
  --ok:     #3B6E2A;

  --radio:   4px;
  --radio-s: 3px;

  --fuente: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono:   "IBM Plex Mono", ui-monospace, monospace;
  --t-xs: 12px; --t-s: 13px; --t-base: 14px; --t-m: 16px; --t-l: 20px; --t-xl: 26px;

  --e1: 4px; --e2: 8px; --e3: 12px; --e4: 16px; --e6: 24px; --e8: 32px;
}
```

Sombra permitida solo en menús desplegables y modales: `0 2px 8px rgba(35,33,30,.12)`.

### 5.3 Prohibiciones de diseño

Este sistema no puede parecer generado por una plantilla. Está prohibido:

- Morado, índigo o violeta como color de marca
- Degradados de cualquier tipo
- `border-radius` mayor a 6 px
- Sombras difusas en tarjetas
- Emojis en la interfaz
- Tres tarjetas de estadística en fila con ícono circular de color
- Texto centrado en pantallas de aplicación
- Inter, Poppins o Montserrat
- Filas de tabla de más de 40 px de alto

### 5.4 Detalles obligatorios

- `font-variant-numeric: tabular-nums` en toda columna de cantidad o dinero
- Fechas en `dd/mm/aaaa`, moneda `RD$ 1,250.00`
- SKU, códigos y hashes en tipografía mono
- Los filtros van en la URL: `?almacen=2&categoria=8&estado=activo`
- Paginación que dice "Mostrando 1–25 de 340"
- Estados vacíos en lenguaje de dominio: "Este almacén no tiene existencias registradas"
- Pie de página con versión y commit corto
- Atajo `/` para enfocar el buscador
- Dos variantes de botón: primario sólido y secundario con borde
- Íconos monocromos de 16 px con trazo de 1.5 px, heredando el color del texto

### 5.5 Componentes reutilizables

Construye estos como plantillas parciales para que los tres módulos los reutilicen sin reinventar nada:

`tabla.html` (ordenable, con selección múltiple) · `barra_filtros.html` · `paginacion.html` · `modal.html` (HTMX) · `badge.html` · `toast.html` · `campo_dinamico.html` · `estado_vacio.html` · `confirmacion.html`

Todos los formularios se envían por HTMX: sin recarga de página, con toast de confirmación. Si el envío falla por red, el formulario conserva los datos y ofrece reintentar (requisito HU-06 de la SRS).

---

## 6. Seguridad

Aplica todo esto desde el primer commit, no al final:

1. Hash de contraseñas con **Argon2** (`django[argon2]`), no el PBKDF2 por defecto.
2. CSRF activo en todos los formularios, incluidos los de HTMX.
3. Solo ORM. Prohibido `raw()`, prohibido concatenar SQL.
4. **Los permisos se verifican en el servidor** en cada vista con un decorador, no solo ocultando botones. Una petición directa por URL sin permiso devuelve 403.
5. Secretos por variable de entorno con `django-environ`. `.env` en `.gitignore`. Se versiona `.env.ejemplo` con los nombres y sin valores.
6. En producción: `DEBUG=False`, `ALLOWED_HOSTS` cerrado, `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SAMESITE=Lax`, `X_FRAME_OPTIONS=DENY`.
7. Límite de intentos de inicio de sesión con **django-axes**: 5 intentos, bloqueo de 30 minutos.
8. Auditoría inmutable, con IP y usuario en cada registro.
9. Validación en cliente **y** en servidor. La del cliente es comodidad; la del servidor es la que manda.
10. `pip-audit` en `requirements-dev.txt` y Dependabot activo en el repositorio.
11. Subida de archivos: extensión y tamaño validados en servidor, nombre saneado.

Estos once puntos son la base del análisis OWASP Top 10 que el equipo tiene que entregar más adelante, así que deja un comentario en el código donde se aplica cada uno.

---

## 7. Despliegue en la nube — costo cero

El sistema tiene que estar en línea para que los cuatro integrantes y el profesor entren desde cualquier navegador.

| Pieza | Servicio | Plan |
|---|---|---|
| Aplicación | **Render** — Web Service | Gratis, 750 h/mes, sin tarjeta. Duerme a los 15 min de inactividad y despierta en 30-60 s |
| Base de datos | **Neon** — PostgreSQL | Gratis permanente, 0.5 GB, 100 CU-hora/mes, sin tarjeta |
| Estáticos | WhiteNoise dentro de Django | Sin costo, sin servicio extra |

No se usa la base de datos gratuita de Render: **expira a los 30 días y se borra.** La de Neon no expira.

Genera:

- `build.sh` con: instalar dependencias, `collectstatic --no-input`, `migrate`.
- `render.yaml` con el servicio web, el comando de arranque con **gunicorn**, y las variables de entorno declaradas sin valores.
- Sección en el `README.md` con los pasos exactos para desplegar y para conectar Neon.

Variables de entorno: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.

---

## 8. Calidad del código

- Docstring en cada módulo, clase y método público. En español.
- Anotaciones de tipo en toda firma de servicio y repositorio.
- Nombres de dominio en español (`Movimiento`, `existencia_actual`), palabras clave de Django en inglés.
- `.pylintrc` con `max-line-length=110` y los avisos de Django desactivados.
- Al menos una prueba por regla de negocio de esta base: autenticación, verificación de permisos, inmutabilidad de la auditoría, validación de campos personalizados.
- Mensajes de commit: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.

`.gitignore` debe excluir `venv`, `__pycache__`, `.env`, `db.sqlite3`, `staticfiles/`, `.pytest_cache`, `htmlcov`. Esto importa: si entra basura al repositorio, el conteo de líneas de código del informe de métricas queda inflado y la interpretación se cae.

---

## 9. Terminado cuando

1. `python manage.py runserver` levanta sin errores.
2. Se entra con el usuario administrador y se ve el panel con la barra lateral.
3. Se crea un rol nuevo, se le asignan permisos y un usuario con ese rol solo ve lo suyo.
4. Se crea un almacén desde la interfaz.
5. Se crea una definición de campo personalizado desde la interfaz y aparece en el formulario correspondiente.
6. Se edita un parámetro del sistema y el cambio se refleja sin reiniciar.
7. Toda acción anterior dejó su registro en la auditoría, y ese registro no se puede editar ni borrar.
8. `pylint apps/ config/` da 8.0 o más.
9. `pytest` pasa en verde.
10. La aplicación está desplegada en Render, conectada a Neon, y responde en su URL pública.

---

## 10. Al terminar

Ejecuta y guarda la salida:

```bash
pylint apps/ config/ --output-format=text > evidencias/pylint_base.txt
pytest --cov=apps --cov-report=term > evidencias/pruebas_base.txt
git log --oneline
```

Captura de pantalla de la aplicación funcionando en su URL pública, con la fecha del sistema visible.
