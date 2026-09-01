# Kardex

Sistema web de gestión de inventario multi-almacén para la **Ferretería M y F, S.R.L.**
Proyecto de la asignatura **INF-5250**, Equipo #3, UASD.

La idea rectora: **el usuario configura el sistema desde la interfaz, no desde el
código.** Categorías, campos, tipos de movimiento, reglas de alerta, roles,
permisos y vistas se definen en pantalla. Agregar un tipo de negocio nuevo no
requiere un despliegue.

El sistema está **completo y en línea**: sobre la base común se construyeron
los tres módulos funcionales (catálogo, movimientos y alertas), ya fusionados
en `main`.

| | |
|---|---|
| **Aplicación en línea** | <https://kardex-aco4.onrender.com> |
| **Repositorio** | <https://github.com/EzequielGomez-code/kardex> (privado) |
| **Base de datos** | Neon PostgreSQL 18, región `us-east-2` |
| **Usuario de prueba** | `admin` |

El servicio gratuito de Render se duerme a los 15 minutos de inactividad. La
primera carga después de un rato tarda entre 30 y 60 segundos en despertar:
es normal, no es un error.

---

## 1. Qué trae el sistema

| Área | Qué incluye |
|---|---|
| `apps/nucleo` | Usuarios, roles, permisos, almacenes y auditoría inmutable |
| `apps/configuracion` | Campos personalizados, parámetros, etiquetas, vistas guardadas, flujos de aprobación, plantillas de notificación y mapeos de importación |
| `apps/catalogo` | Categorías en árbol, artículos con SKU generado, marcas, unidades, proveedores, clientes e importación masiva por CSV — **Arturo** |
| `apps/movimientos` | Entradas, salidas, transferencias y ajustes, valoración PEPS por lotes, existencias, kardex, aprobaciones y anulación por contrapartida — **Cristian** |
| `apps/alertas` | Reglas configurables, evaluación automática y reportes en PDF y Excel — **Francisco** |
| `plantillas/componentes` | Tabla, filtros, paginación, modal, badge, toast, campo dinámico, estado vacío y confirmación |
| `estaticos/css` | Sistema de diseño propio con variables; sin Tailwind ni Bootstrap |

---

## 2. Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Framework | Django 5.2 |
| Base de datos | PostgreSQL (Neon) en la nube · SQLite en local |
| Interactividad | HTMX 2 + Alpine.js 3, servidos como estáticos locales |
| Estilos | CSS propio con variables |
| Estáticos | WhiteNoise |
| Formularios | Escritos a mano (el brief lo permite; el diseño propio necesita control del marcado) |
| Configuración | django-environ |
| Pruebas | pytest-django + coverage |
| Análisis estático | Pylint + Ruff |

Sin npm, sin `node_modules`, sin frameworks de CSS, sin servicios de pago,
sin credenciales en el código.

---

## 3. Puesta en marcha local

```bash
git clone <url-del-repositorio> kardex
cd kardex
```

Cree el entorno virtual con Python 3.12:

```bash
python -m venv venv
```

Actívelo — en Windows con PowerShell:

```bash
venv\Scripts\Activate.ps1
```

En Linux o macOS:

```bash
source venv/bin/activate
```

Instale las dependencias de desarrollo:

```bash
pip install -r requirements-dev.txt
```

Copie la plantilla de variables de entorno y complete los valores:

```bash
cp .env.ejemplo .env
```

Como mínimo, `.env` necesita:

```
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=<genere una>
DJANGO_DEBUG=True
DJANGO_ADMIN_PASSWORD=<la que usará para entrar>
```

Genere la clave secreta con:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Deje `DATABASE_URL` vacío para trabajar contra SQLite. Luego:

```bash
python manage.py migrate
```

```bash
python manage.py sembrar
```

```bash
python manage.py runserver
```

Abra <http://127.0.0.1:8000/> y entre con el usuario `admin` y la contraseña
que puso en `DJANGO_ADMIN_PASSWORD`. Si dejó esa variable vacía, el comando
`sembrar` genera una contraseña al azar y la muestra **una sola vez**.

---

## 4. Comandos de trabajo

| Para | Comando |
|---|---|
| Levantar el servidor | `python manage.py runserver` |
| Cargar datos iniciales | `python manage.py sembrar` |
| Correr las pruebas | `pytest` |
| Pruebas con cobertura | `pytest --cov=apps --cov-report=term` |
| Análisis estático | `pylint apps/ config/` |
| Formato y orden de importaciones | `ruff check apps/ config/ --fix` |
| Auditoría de dependencias | `pip-audit -r requirements.txt` |

---

## 5. Reglas de arquitectura

**Regla de capas, sin excepciones:**

```
vista  →  servicio  →  repositorio  →  base de datos
```

- Ninguna vista hace `Model.objects.filter(...)` directamente.
- Ningún repositorio contiene reglas de negocio.
- Los servicios son los únicos que escriben en la auditoría.

**Nombres:** dominio en español (`Movimiento`, `existencia_actual`), palabras
clave de Django en inglés (`models.py`, `views.py`, `register`, `Meta`).

**Menú lateral:** cada app declara sus entradas en `apps/<app>/navegacion.py`.
El layout las recoge solo, filtradas por permiso. Nadie edita `base.html`.

**Campos personalizados:** para colgar campos propios de sus modelos, use
`ServicioCamposPersonalizados`:

```python
from apps.configuracion.services import ServicioCamposPersonalizados

campos = ServicioCamposPersonalizados.campos_de("Articulo", categoria)
ServicioCamposPersonalizados.guardar_valores(articulo, request.POST)
valores = ServicioCamposPersonalizados.valores_de(articulo)
```

**Parámetros del sistema:** nada de números mágicos en el código.

```python
from apps.configuracion.services import ServicioParametros

if not ServicioParametros.obtener("permitir_stock_negativo", False):
    ...
```

---

## 6. Seguridad aplicada

Los once puntos del brief, cada uno marcado con un comentario en el código:

| # | Medida | Dónde |
|---|---|---|
| 1 | Hash Argon2 | `config/settings/base.py` → `PASSWORD_HASHERS` |
| 2 | CSRF activo, también en HTMX | `plantillas/base.html`, `estaticos/js/kardex.js` |
| 3 | Solo ORM; sin `raw()` ni SQL concatenado | `apps/*/repositories.py` |
| 4 | Permisos verificados en el servidor | `apps/nucleo/decoradores.py` |
| 5 | Secretos por variable de entorno | `config/settings/base.py`, `.env.ejemplo` |
| 6 | Cabeceras y cookies seguras en producción | `config/settings/produccion.py` |
| 7 | Límite de intentos de acceso (django-axes) | `config/settings/base.py` → `AXES_*` |
| 8 | Auditoría inmutable con IP y usuario | `apps/nucleo/models.py` → `RegistroAuditoria` |
| 9 | Validación en cliente y en servidor | `apps/configuracion/services.py` |
| 10 | `pip-audit` en `requirements-dev.txt` | `requirements-dev.txt` |
| 11 | Subidas: extensión, tamaño y nombre saneado | `apps/nucleo/utilidades.py` |

Estos once puntos son la base del análisis OWASP Top 10 que entrega el equipo.

---

## 7. Despliegue en la nube — costo cero

| Pieza | Servicio | Plan |
|---|---|---|
| Aplicación | Render — Web Service | Gratis, 750 h/mes, sin tarjeta |
| Base de datos | Neon — PostgreSQL | Gratis permanente, 0.5 GB, sin tarjeta |
| Estáticos | WhiteNoise dentro de Django | Sin costo |

**No se usa la base de datos gratuita de Render: expira a los 30 días y se
borra.** La de Neon no expira.

El servicio gratuito de Render se duerme a los 15 minutos de inactividad y
tarda entre 30 y 60 segundos en despertar. Es normal; no es un error.

### 7.1 Preparar Neon

1. Cree una cuenta en <https://neon.com> y un proyecto nuevo.
2. En **Connection Details**, copie la cadena de conexión. Tiene esta forma:
   `postgresql://USUARIO:CLAVE@HOST.neon.tech/neondb?sslmode=require`
3. Guárdela: es el valor de `DATABASE_URL` en Render.

### 7.2 Subir el código a GitHub

Render despliega desde un repositorio Git. Cree uno **privado** en su cuenta y
publique la rama `main`:

```bash
git remote add origin https://github.com/<usuario>/kardex.git
```

```bash
git push -u origin main
```

### 7.3 Crear el servicio en Render

1. Entre a <https://dashboard.render.com> y elija **New → Web Service**.
2. Conecte el repositorio de GitHub.
3. Render lee `render.yaml` y propone la configuración. Confirme que quede así:
   - **Runtime:** Python 3
   - **Build Command:** `./build.sh`
   - **Start Command:** `gunicorn config.wsgi:application --workers 2 --threads 4 --timeout 60`
   - **Plan:** Free
4. En **Environment**, cargue las variables que `render.yaml` deja sin valor:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | la cadena de Neon del paso 7.1 |
   | `ALLOWED_HOSTS` | `kardex.onrender.com` (el host que le asigne Render) |
   | `CSRF_TRUSTED_ORIGINS` | `https://kardex.onrender.com` |
   | `DJANGO_ADMIN_PASSWORD` | la contraseña del administrador inicial |
   | `SEMBRAR_AL_DESPLEGAR` | `true` — y se queda así (ver 7.4) |

   `DJANGO_SECRET_KEY` la genera Render sola. `DJANGO_SETTINGS_MODULE` ya viene
   fijada en `config.settings.produccion`.

5. **Create Web Service.** El primer despliegue tarda unos minutos.

### 7.4 `SEMBRAR_AL_DESPLEGAR` se queda en `true`

`build.sh` solo corre `python manage.py sembrar` cuando esa variable vale
`true`. Conviene dejarla encendida siempre, y no apagarla tras el primer
despliegue.

El motivo: `sembrar` no es solo un arranque inicial. Carga el fixture
`permisos_roles.json`, que es **configuración viva** — cada función nueva
agrega sus permisos ahí. Con la variable apagada, el fixture del repositorio
sigue creciendo mientras la base se queda con los permisos del primer día, y
los roles que no son superusuario empiezan a recibir 403 en pantallas que sí
deberían poder usar. Eso pasó en este proyecto: producción se quedó con 14 de
25 permisos, y solo se notó cuando alguien entró con el rol «Gerente de
almacén», porque el administrador es superusuario y no pasa por esa
comprobación.

El comando es idempotente: busca antes de crear y respeta lo que ya se editó
a mano, así que correrlo en cada despliegue no duplica ni pisa nada.

### 7.5 Comprobar

Abra `https://<su-servicio>.onrender.com/` y entre con `admin` y la contraseña
que cargó. Si ve la pantalla de acceso con la barra verde a la izquierda, quedó
desplegado.

### 7.6 Estado actual del despliegue

Ya está montado y en línea:

| Pieza | Valor |
|---|---|
| Servicio Render | `kardex` (plan Free, región Oregon) |
| URL pública | <https://kardex-aco4.onrender.com> |
| Despliegue automático | activado en cada `push` a `main` |
| Base de datos | Neon, ya migrada y sembrada |
| `SEMBRAR_AL_DESPLEGAR` | `true` — re-sincroniza permisos y roles en cada despliegue (ver 7.4) |

Render asignó el sufijo `-aco4` porque el nombre `kardex` ya estaba tomado por
otra cuenta. `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` apuntan a ese host; además,
`config/settings/produccion.py` añade solo el valor de `RENDER_EXTERNAL_HOSTNAME`,
así que el sistema sigue funcionando si el host cambia.

---

## 8. Terminado cuando

- [x] `python manage.py runserver` levanta sin errores
- [x] Se entra con el administrador y se ve el panel con la barra lateral
- [x] Se crea un rol, se le asignan permisos y un usuario con ese rol solo ve lo suyo
- [x] Se crea un almacén desde la interfaz
- [x] Se crea un campo personalizado y aparece en el formulario correspondiente
- [x] Se edita un parámetro y el cambio se refleja sin reiniciar
- [x] Toda acción quedó en la auditoría, y ese registro no se puede editar ni borrar
- [x] `pylint apps/ config/` da 10.00/10 (el mínimo exigido era 8.0)
- [x] `ruff check apps/ config/` sin hallazgos
- [x] `pytest` pasa en verde — 272 pruebas
- [x] Desplegada en Render, conectada a Neon y respondiendo en <https://kardex-aco4.onrender.com>

Las evidencias de las corridas están en `evidencias/`.

---

## 9. Para los compañeros de equipo

Los tres módulos ya están construidos y fusionados en `main`. Para seguir
trabajando sobre ellos, abra una rama por cambio:

```bash
git checkout -b arregla-lo-que-sea
```

Cada app tiene `models.py`, `views.py`, `urls.py`, `services.py`,
`repositories.py`, `admin.py`, `navegacion.py`, su carpeta de plantillas y su
carpeta de pruebas. Respete la regla de capas del punto 5: una vista nunca
consulta el ORM.

Antes de abrir un pull request:

```bash
pytest && pylint apps/ config/ && ruff check apps/ config/
```

Mensajes de commit: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
