# Informe de Verificación y Validación (V&V) — Kardex

**Asignatura:** INF-5250 Ingeniería de Software II — Unidad 3
**Proyecto:** Kardex (sistema de control de inventario e existencias)
**Fecha:** 05/09/2026

## 1. Contexto del sistema medido

Kardex es una aplicación Django en producción (Render + Neon), con capas
`vista → servicio → repositorio → base de datos` según `RULES.md`. Este
informe corresponde a la versión congelada en el commit indicado abajo,
rama `main`.

| Parámetro de verificación | Valor |
|---|---|
| Repositorio | https://github.com/EzequielGomez-code/kardex |
| Rama analizada | main |
| Commit Hash | `07f08e9` |
| Estado del árbol de trabajo | limpio, sincronizado con `origin/main` |
| Fecha de corte | 05/09/2026 |
| Sistema de control de versiones | Git |

## 2. Verificación vs. Validación: definiciones y ejemplo real del proyecto

**Verificación** responde a la pregunta *¿estamos construyendo el producto
correctamente?* Se hace **sin ejecutar** el programa: se inspecciona el
código fuente en busca de defectos, convenciones violadas o construcciones
riesgosas. Es barata, rápida y se puede automatizar por completo.

**Validación** responde a *¿estamos construyendo el producto correcto?* Se
hace **ejecutando** el sistema y comprobando que su comportamiento cumple lo
que el usuario necesita. Es más costosa, pero es la única que confirma que
el software realmente funciona como se espera.

### Ejemplo tomado del propio repositorio

- **Verificación (análisis estático con Pylint).** El archivo de
  demostración `evidencias/vv/demo_estatico_antes.py` nunca se ejecuta y aun
  así Pylint detecta 4 defectos con solo leer el texto del programa: dos
  imports sin usar, una variable sin usar y una cláusula `except` sin tipo
  (que podría esconder errores graves). Ese es el rol de la inspección
  automática dentro del ciclo de vida: atrapar defectos **antes** de que el
  código corra siquiera una vez.
- **Validación (pruebas automatizadas con pytest).** La prueba
  [`test_guardar_campos_personalizados_deja_rastro_en_la_auditoria`](../../pruebas/test_campos_personalizados.py)
  sí **ejecuta** el sistema completo (guarda un campo personalizado en un
  Almacén) y confirma que ocurre lo que el punto 9.7 del brief exige: que
  la acción deje un registro en `RegistroAuditoria`. Ningún analizador
  estático puede confirmar eso — solo correr el sistema lo demuestra.
- **Rol de la inspección manual.** La ronda de revisión técnica cruzada con
  otro equipo (ver `checklist_revision_tecnica.md`) es una forma de
  **verificación manual**: complementa lo que Pylint no puede ver (¿tiene
  sentido de negocio esta regla?, ¿la capa de servicio realmente no
  filtra reglas al repositorio?).

## 3. Herramientas utilizadas

| Herramienta | Versión | Comando exacto |
|---|---|---|
| Pylint (+ pylint-django) | 3.3.7 (astroid 3.3.11) | `pylint apps/ config/ --output-format=text` |
| pytest (+ pytest-cov) | ver `requirements-dev.txt` | `pytest --cov=apps --cov-report=term` |
| Ruff | ver `requirements-dev.txt` | `ruff check apps/ config/ pruebas/ conftest.py manage.py` |

Configuración de Pylint: `.pylintrc` en la raíz del repositorio (umbral
exigido por el brief: 8.0/10; línea máxima 110 caracteres; reglas
específicas de Django desactivadas — ver comentarios en el archivo).

## 4. Resultados

| Herramienta | Resultado | Evidencia |
|---|---|---|
| Pylint sobre `apps/` y `config/` | **10.00/10**, cero hallazgos | `pylint_salida.txt` |
| pytest con cobertura | **272 pruebas en verde**, 76% de cobertura sobre `apps/` | `pytest_salida.txt` |
| Ruff | **sin hallazgos** | `ruff_salida.txt` |
| Pylint sobre archivo de demo con defectos inyectados | 4 hallazgos, **5.56/10** | `demo_estatico_antes_salida.txt` |
| Pylint sobre el mismo archivo, corregido | **10.00/10** | `demo_estatico_despues_salida.txt` |

## 5. Interpretación

El código de producción (`apps/`, `config/`) mantiene 10.00/10 en Pylint de
forma sostenida — no es un resultado de una sola corrida, sino la
consecuencia de una regla de `RULES.md` que exige correr Pylint al cierre
de cada fase de trabajo, antes de continuar. Eso es verificación aplicada
como práctica continua, no como trámite final.

Que el reporte esté "limpio" no significa que el análisis estático no
tenga valor aquí: el archivo de demostración prueba que la herramienta sí
detecta problemas reales cuando existen (imports muertos, una variable que
se calcula y se descarta, un `except` que oculta cualquier error). La
ausencia de hallazgos en el código real es evidencia de que esa disciplina
se aplicó desde el principio, no de que la herramienta sea permisiva.

La validación (pytest) es el complemento necesario: confirma **comportamiento**
que ningún análisis estático puede evaluar, como que una acción de negocio
deje rastro en la auditoría, o que un campo obligatorio realmente bloquee
el guardado. El 76% de cobertura indica dónde la validación es más débil —
notablemente `views.py` (42%) y `services.py` (66%) en `nucleo` — lo cual es
un insumo directo para priorizar próximas pruebas, no un defecto del informe.

## 6. Conclusiones y próximos pasos

- El código base cumple y supera el umbral exigido (10.00/10 sobre un
  mínimo de 8.0) tanto en verificación estática como en las pruebas
  dinámicas de validación.
- Antes de la próxima entrega, ampliar cobertura en `apps/nucleo/views.py`
  y `apps/nucleo/services.py`, las áreas con menor porcentaje de pruebas.
- Los hallazgos de la ronda de revisión cruzada con otro equipo (Sección
  siguiente) se documentan en `plantilla_acta_revision.md` y alimentan la
  entrega parcial correspondiente.

## 7. Fuentes consultadas

- Sommerville, I. *Ingeniería del Software*, 7ma ed. — capítulos de
  verificación y validación, e inspección de software.
- Documentación oficial de Pylint (pylint.readthedocs.io) y pylint-django.
- `RULES.md` y `.pylintrc` de este repositorio (fuente primaria de las
  reglas aplicadas).

## Anexos

- `pylint_salida.txt`, `pytest_salida.txt`, `ruff_salida.txt` — salida cruda
  de las tres herramientas sobre el código de producción.
- `demo_estatico_antes.py` / `demo_estatico_antes_salida.txt` — archivo con
  defectos inyectados a propósito y su detección.
- `demo_estatico_despues.py` / `demo_estatico_despues_salida.txt` — mismo
  archivo, corregido, en 10.00/10.
- `historial_git.txt` — historial de commits al momento del corte.
