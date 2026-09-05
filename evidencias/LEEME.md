# Evidencias de Kardex

Salidas generadas con los comandos del punto 10 del brief. Dos cortes: la
base original (antes del BRIEF 02) y el cierre de las 8 fases del rediseño
visual y los tres módulos funcionales.

## Base (antes del BRIEF 02)

| Archivo | Comando | Resultado |
|---|---|---|
| `pylint_base.txt` | `pylint apps/ config/ --output-format=text` | 10.00/10 (mínimo exigido: 8.0) |
| `pruebas_base.txt` | `pytest --cov=apps --cov-report=term` | 74 pruebas en verde, 73% de cobertura |
| `ruff_base.txt` | `ruff check apps/ config/ pruebas/ conftest.py manage.py` | sin hallazgos |
| `historial_git.txt` | `git log --oneline` | 9 commits con prefijos convencionales |

## Final (cierre de la Fase 8)

| Archivo | Comando | Resultado |
|---|---|---|
| `pylint_final.txt` | `pylint apps/ config/ --output-format=text` | 10.00/10 |
| `pruebas_final.txt` | `pytest --cov=apps --cov-report=term` | 253 pruebas en verde, 72% de cobertura |
| `ruff_final.txt` | `ruff check apps/ config/ pruebas/ conftest.py manage.py` | sin hallazgos |
| `historial_git_final.txt` | `git log --oneline` | 26 commits con prefijos convencionales |
| `auditoria_botones.md` | Recorrido manual de la Fase 7 | sin botones muertos, dos correcciones de ordenamiento |
| `seguridad.md` | Verificación de los once puntos de seguridad del brief base | los once siguen aplicando |
| `despliegue.md` | URL pública y verificación de arranque | ver sección propia |

La captura de pantalla de la aplicación en su URL pública se toma una vez
desplegada de nuevo en Render con todo lo construido esta sesión (ver
`despliegue.md`).

## Unidad 3 — Verificación y Validación (`vv/`)

Evidencia de la demostración de V&V (commit `07f08e9`, rama `main`).

| Archivo | Comando | Resultado |
|---|---|---|
| `vv/pylint_salida.txt` | `pylint apps/ config/ --output-format=text` | 10.00/10 |
| `vv/pytest_salida.txt` | `pytest --cov=apps --cov-report=term` | 272 pruebas en verde, 76% de cobertura |
| `vv/ruff_salida.txt` | `ruff check apps/ config/ pruebas/ conftest.py manage.py` | sin hallazgos |
| `vv/demo_estatico_antes.py` + `_salida.txt` | Pylint sobre un archivo con defectos inyectados a propósito | 4 hallazgos, 5.56/10 |
| `vv/demo_estatico_despues.py` + `_salida.txt` | El mismo archivo, corregido | 10.00/10 |
| `vv/historial_git.txt` | `git log --oneline` | historial completo al corte |
| `vv/informe_vv.md` | Informe escrito de V&V con interpretación | — |
| `vv/checklist_revision_tecnica.md` | Checklist para la ronda de revisión cruzada | — |
| `vv/plantilla_acta_revision.md` | Acta a llenar en vivo con el equipo revisor | — |

### Reportes con formato para presentar (`vv/demo_clase/`)

Pensado para la demostración en clase: clonar el repo, generar estos
reportes en vivo y volver a subirlos. `generar_reporte_pylint.py` convierte
la salida de Pylint (que por defecto es texto plano) en una página HTML
legible; `pytest --html=... --self-contained-html` usa el plugin
`pytest-html` (ya en `requirements-dev.txt`) para lo mismo con pytest.

| Archivo | Cómo se generó | Resultado |
|---|---|---|
| `demo_clase/generar_reporte_pylint.py` | Script propio: corre `pylint --output-format=json2` y arma el HTML | — |
| `demo_clase/test_demo_fallo.py` | Prueba aislada con un caso que falla a propósito | 1 en verde, 1 en rojo |
| `demo_clase/reporte_pylint_v01.html` | Generador sobre `apps/` y `config/` (código real) | 10.00/10 |
| `demo_clase/reporte_pylint_v02.html` | Generador sobre un archivo con defectos a propósito | 4 hallazgos, 5.56/10 |
| `demo_clase/reporte_pytest_v01.html` | `pytest --html=... --self-contained-html` sobre la suite real | 272 en verde |
| `demo_clase/reporte_pytest_v02.html` | Lo mismo sobre `test_demo_fallo.py` | 1 en verde, 1 en rojo |

Estos cuatro reportes `v01`/`v02` son de referencia (generados una vez para
dejar constancia de que la herramienta funciona); al repetir la
demostración en clase se pueden volver a generar con el mismo nombre
(se reemplazan) o con un sufijo de versión nuevo (`v03`, `v04`...).
