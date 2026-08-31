# Kardex — reglas permanentes

Estas reglas aplican a toda sesión de trabajo sobre este repositorio, no solo a la que las escribió.

## Commits

- **Sin líneas de co-autoría ni menciones de ninguna herramienta de asistencia en los mensajes de commit.** El único autor es el dueño de la cuenta.
- Formato: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `style:`. Una línea, en español, describiendo el cambio real.
- Se crea un commit por fase de trabajo terminada, nunca a mitad de una fase rota.

## Regla de capas — sin excepciones

```
vista  →  servicio  →  repositorio  →  base de datos
```

- Ninguna vista consulta el ORM directamente.
- Ningún repositorio contiene reglas de negocio.
- Los servicios son los únicos que escriben en la auditoría (`ServicioAuditoria.registrar`).

## Nombres

Dominio en español (`Movimiento`, `existencia_actual`, `ServicioValoracion`). Palabras clave de Django en inglés (`models.py`, `views.py`, `register`, `Meta`, `save`, `clean`).

## Diseño — prohibiciones permanentes

- Morado, índigo o violeta como color de marca
- Degradados de cualquier tipo
- Radios de esquina mayores a 6 px
- Sombras difusas en tarjetas (solo `--sombra-flotante` en desplegables y modales)
- Emojis en la interfaz
- Tres tarjetas de estadística en fila con ícono circular de color
- Texto centrado en pantallas de aplicación
- Inter, Poppins o Montserrat
- Filas de tabla de más de 40 px de alto
- Controles de formulario con la apariencia por defecto del navegador
- Cualquier framework de CSS, cualquier dependencia de npm

Todo color, tamaño y espacio sale de `estaticos/css/tokens.css`. Ninguna pantalla define un valor a mano.

## Botones muertos — prohibido

Si una función no está construida, el botón no existe. No se dejan controles decorativos, enlaces a anclas vacías, ni la palabra "próximamente" en ninguna parte de la interfaz.

## Trabajo por fases

Termina y corre las pruebas y el analizador estático de una fase antes de pasar a la siguiente. No se avanza si la anterior no corre.

Al cierre de cada fase: `pytest`, `pylint apps/ config/`, `ruff check apps/ config/`.
