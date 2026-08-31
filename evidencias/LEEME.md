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
