# Coevaluación de código: Kardex · Equipo #3

Este repositorio es una copia de Kardex hecha para la revisión técnica cruzada
entre equipos (Entregable 2, Actividad 1). Aquí no se programa: es la versión
congelada que ustedes revisan.

| Dato | Valor |
|---|---|
| Sistema | Kardex, inventario multialmacén para la Ferretería M y F, S.R.L. |
| Versión revisada | etiqueta `v0.2-coevaluacion` |
| Módulo a revisar | `apps/movimientos` (movimientos de inventario y valoración PEPS) |
| Aplicación en línea | https://kardex-aco4.onrender.com (tarda hasta un minuto en despertar) |
| Coordinador | Ezequiel Gómez Cepeda |

## Qué hay en el módulo

| Archivo | Qué hace |
|---|---|
| `models.py` | Movimientos, sus líneas, lotes y existencias |
| `services.py` | Registrar entradas, salidas, transferencias y ajustes; anular; aprobar |
| `valoracion.py` | Cálculo PEPS: qué lotes salen primero y a qué costo |
| `repositories.py` | Consultas a la base de datos |
| `views.py` | Pantallas del módulo |
| `forms.py` | Formularios y validación de los datos que escribe el usuario |
| `urls.py`, `navegacion.py`, `admin.py` | Rutas, menú y administración |
| `pruebas/` | Pruebas automáticas del módulo |

La regla del proyecto es: vista → servicio → repositorio → base de datos.

## Checklist (15 ítems)

1. Los nombres de clases, métodos y variables dicen qué hacen.
2. No hay funciones de más de 40 líneas ni con más de 5 parámetros.
3. No hay código duplicado que debería estar en un método común.
4. Las vistas no consultan la base de datos directamente.
5. Ninguna clase usa detalles internos de otra.
6. Las entradas del usuario se validan en el servidor.
7. Se contemplan valores vacíos, nulos, en cero o negativos.
8. Las excepciones se capturan y se informan; no hay `except` vacíos.
9. No hay credenciales, claves ni rutas absolutas en el código.
10. Las consultas usan el ORM o parámetros, nunca texto concatenado.
11. La salida consume los lotes del más antiguo al más reciente (PEPS).
12. La existencia nunca queda negativa y un movimiento confirmado no se edita ni se borra.
13. Cada movimiento queda en la auditoría con usuario, fecha y hora.
14. Cada regla de negocio tiene al menos una prueba automática.
15. El módulo se entiende sin preguntarle al autor.

## Cómo registrar un hallazgo

1. Entren a la pestaña **Issues** de este repositorio y pulsen **New issue**.
2. Elijan la plantilla **Hallazgo de revisión** y llenen el número del ítem,
   el archivo y la línea, qué encontraron y su clasificación.
3. Clasificación: **mayor** (rompe una regla de negocio o abre un riesgo de
   seguridad), **menor** (legibilidad o mantenimiento) o **sugerencia**.

Cada issue queda con su cuenta y su fecha: esa es la evidencia de la revisión.
