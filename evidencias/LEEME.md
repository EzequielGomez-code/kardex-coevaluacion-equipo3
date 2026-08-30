# Evidencias de la base de Kardex

Salidas generadas con los comandos del punto 10 del brief.

| Archivo | Comando | Resultado |
|---|---|---|
| `pylint_base.txt` | `pylint apps/ config/ --output-format=text` | 10.00/10 (mínimo exigido: 8.0) |
| `pruebas_base.txt` | `pytest --cov=apps --cov-report=term` | 74 pruebas en verde, 73% de cobertura |
| `ruff_base.txt` | `ruff check apps/ config/ pruebas/ conftest.py manage.py` | sin hallazgos |
| `historial_git.txt` | `git log --oneline` | 9 commits con prefijos convencionales |

Falta la captura de pantalla de la aplicación en su URL pública, que se toma
una vez desplegada en Render (ver sección 7 del README).
