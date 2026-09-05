# Checklist de revisión técnica formal cruzada

**Uso:** este checklist lo aplica un equipo **distinto** al dueño del
código (revisión cruzada), moderada por un integrante del equipo dueño.
Cada fila se marca ✅ (cumple), ⚠️ (cumple con observación) o ❌ (no
cumple), con un comentario breve si no es ✅. Los hallazgos ⚠️/❌ pasan a la
tabla de hallazgos del acta.

## 1. Preparación (antes de la ronda)

- [ ] El commit a revisar está identificado por hash y es el mismo que
      corrieron las herramientas automáticas.
- [ ] El equipo revisor recibió, con antelación, el informe de V&V
      (`informe_vv.md`) y acceso al repositorio.
- [ ] Se definieron los roles: moderador, revisor(es), quien redacta el
      acta.

## 2. Análisis estático (verificación automática)

| # | Criterio | Estado | Comentario |
|---|---|---|---|
| 2.1 | Pylint corre sin errores de configuración y reporta ≥ 8.0/10 | | |
| 2.2 | Ruff no reporta hallazgos sin justificar | | |
| 2.3 | No hay código muerto evidente (funciones/variables sin uso que Pylint no detectó por ser dinámico) | | |

## 3. Diseño y capas (`RULES.md`)

| # | Criterio | Estado | Comentario |
|---|---|---|---|
| 3.1 | Ninguna vista revisada consulta el ORM directamente | | |
| 3.2 | Los repositorios no contienen reglas de negocio | | |
| 3.3 | Los servicios son los únicos que escriben en la auditoría | | |
| 3.4 | Los nombres de dominio están en español; las palabras clave de Django, en inglés | | |

## 4. Seguridad y datos

| # | Criterio | Estado | Comentario |
|---|---|---|---|
| 4.1 | Las validaciones de campos obligatorios/tipo ocurren del lado del servidor, no solo en el navegador | | |
| 4.2 | Las acciones sensibles (crear, editar, eliminar) quedan en `RegistroAuditoria` | | |
| 4.3 | No hay credenciales, tokens o cadenas de conexión escritas directamente en el código revisado | | |

## 5. Pruebas y validación dinámica

| # | Criterio | Estado | Comentario |
|---|---|---|---|
| 5.1 | pytest corre en verde sobre la versión congelada | | |
| 5.2 | La cobertura reportada es razonable para el módulo revisado, o se explica por qué no | | |
| 5.3 | Existe al menos una prueba que valida el requisito de negocio revisado (no solo que "no truene") | | |

## 6. Legibilidad y mantenibilidad

| # | Criterio | Estado | Comentario |
|---|---|---|---|
| 6.1 | Los nombres de funciones/variables comunican su propósito sin necesitar comentario aparte | | |
| 6.2 | No hay funciones que mezclen claramente más de una responsabilidad | | |
| 6.3 | Los mensajes de commit siguen el formato acordado y describen el cambio real | | |

## Cierre de la ronda

- [ ] Todos los hallazgos ⚠️/❌ quedaron registrados en la tabla de la
      **acta de revisión** (`plantilla_acta_revision.md`), con responsable
      y acción acordada.
- [ ] Se acordó una disposición final: **Aprobado**, **Aprobado con
      observaciones** o **Rechazado** (requiere nueva ronda).
- [ ] El acta quedó firmada (o confirmada por escrito) por moderador y
      revisor(es).
