"""Genera un reporte HTML legible a partir de la salida de Pylint.

Pylint no trae un formato HTML propio que se vea bien para presentar, así
que este script corre Pylint con su formato ``json2`` (mensajes + puntaje
en una sola llamada) y arma una página HTML autocontenida: sin
dependencias externas, sin conexión a internet, para que funcione igual en
el salón de clase que en una computadora sin nada instalado más que
Python y Pylint.

Uso:
    python generar_reporte_pylint.py <ruta> [<ruta> ...] --salida archivo.html [--titulo "texto"]

Ejemplo real de este proyecto:
    python evidencias/vv/demo_clase/generar_reporte_pylint.py apps config ^
        --salida evidencias/vv/demo_clase/reporte_pylint_v01.html ^
        --titulo "v01 - codigo original"
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import subprocess
import sys
from pathlib import Path

UMBRAL_MINIMO = 8.0

ORDEN_SEVERIDAD = ["fatal", "error", "warning", "refactor", "convention", "info"]

ETIQUETA_SEVERIDAD = {
    "fatal": "Fatal",
    "error": "Error",
    "warning": "Aviso",
    "refactor": "Refactor",
    "convention": "Convención",
    "info": "Info",
}


def correr_pylint(rutas: list[str]) -> dict:
    """Ejecuta Pylint sobre las rutas dadas y devuelve el reporte ``json2``."""
    entorno = os.environ.copy()
    entorno.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    entorno["PYTHONPATH"] = "." + os.pathsep + entorno.get("PYTHONPATH", "")

    comando = [sys.executable, "-m", "pylint", *rutas, "--output-format=json2"]
    resultado = subprocess.run(
        comando, capture_output=True, text=True, env=entorno, check=False
    )
    try:
        return json.loads(resultado.stdout)
    except json.JSONDecodeError as error:
        print("No se pudo interpretar la salida de Pylint:", file=sys.stderr)
        print(resultado.stdout, file=sys.stderr)
        print(resultado.stderr, file=sys.stderr)
        raise SystemExit(1) from error


def clase_puntaje(puntaje: float) -> str:
    if puntaje >= UMBRAL_MINIMO:
        return "ok"
    if puntaje >= 5.0:
        return "alerta"
    return "riesgo"


def fila_hallazgo(mensaje: dict) -> str:
    severidad = mensaje.get("type", "info")
    ubicacion = f"{mensaje.get('path', '')}:{mensaje.get('line', '?')}"
    return f"""
      <tr>
        <td><span class="pastilla {html.escape(severidad)}">{html.escape(ETIQUETA_SEVERIDAD.get(severidad, severidad))}</span></td>
        <td class="mono">{html.escape(ubicacion)}</td>
        <td class="mono">{html.escape(mensaje.get('messageId', ''))}</td>
        <td class="mono">{html.escape(mensaje.get('symbol', ''))}</td>
        <td>{html.escape(mensaje.get('message', ''))}</td>
      </tr>"""


def construir_html(reporte: dict, rutas: list[str], titulo: str) -> str:
    estadisticas = reporte.get("statistics", {})
    puntaje = estadisticas.get("score", 0.0) or 0.0
    conteos = estadisticas.get("messageTypeCount", {})
    mensajes = reporte.get("messages", [])
    mensajes_ordenados = sorted(
        mensajes,
        key=lambda m: (ORDEN_SEVERIDAD.index(m.get("type", "info")) if m.get("type") in ORDEN_SEVERIDAD else 99, m.get("path", ""), m.get("line", 0)),
    )
    ahora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    comando = "pylint " + " ".join(rutas) + " --output-format=json2"
    clase_score = clase_puntaje(puntaje)

    filas_conteo = "".join(
        f'<div class="conteo__item"><span class="conteo__num">{conteos.get(sev, 0)}</span>'
        f'<span class="conteo__etq">{ETIQUETA_SEVERIDAD[sev]}</span></div>'
        for sev in ORDEN_SEVERIDAD
    )

    if mensajes_ordenados:
        cuerpo_tabla = "".join(fila_hallazgo(m) for m in mensajes_ordenados)
        tabla_html = f"""
        <table class="datos">
          <thead><tr><th>Severidad</th><th>Ubicación</th><th>Código</th><th>Regla</th><th>Mensaje</th></tr></thead>
          <tbody>{cuerpo_tabla}</tbody>
        </table>"""
    else:
        tabla_html = '<div class="vacio">✅ Sin hallazgos — Pylint no encontró ningún problema en el código analizado.</div>'

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<style>
  :root{{
    --papel:#F2F4F1; --tinta:#1B2420; --tinta-suave:#42504A; --texto-2:#63706A;
    --linea:#D2D9D1; --marca:#1F5B4E; --marca-fuerte:#153F36; --marca-tenue:#DEE9E4;
    --ok:#1F5B4E; --ok-fondo:#DEE9E4; --alerta:#8A5A16; --alerta-fondo:#F3E7D3;
    --riesgo:#8C2F2F; --riesgo-fondo:#F4DEDE;
  }}
  *{{box-sizing:border-box;}}
  body{{background:var(--papel);color:var(--tinta);font-family:system-ui,Segoe UI,Arial,sans-serif;
       line-height:1.5;margin:0;padding:32px 20px 60px;}}
  .envoltura{{max-width:900px;margin:0 auto;}}
  .mono{{font-family:ui-monospace,Consolas,"Courier New",monospace;font-size:.86rem;}}
  header{{border-bottom:1px solid var(--linea);padding-bottom:20px;margin-bottom:22px;}}
  .eyebrow{{font-family:ui-monospace,Consolas,monospace;font-size:.75rem;letter-spacing:.08em;
           text-transform:uppercase;color:var(--marca-fuerte);margin-bottom:8px;}}
  h1{{font-size:1.5rem;margin:0 0 6px;}}
  .meta{{color:var(--texto-2);font-size:.86rem;}}
  .panel{{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin:20px 0 26px;}}
  .score{{border-radius:8px;padding:14px 22px;text-align:center;min-width:120px;}}
  .score .num{{font-size:2.2rem;font-weight:700;line-height:1;}}
  .score .etq{{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;opacity:.85;}}
  .score.ok{{background:var(--ok-fondo);color:var(--marca-fuerte);}}
  .score.alerta{{background:var(--alerta-fondo);color:var(--alerta);}}
  .score.riesgo{{background:var(--riesgo-fondo);color:var(--riesgo);}}
  .conteos{{display:flex;gap:18px;flex-wrap:wrap;}}
  .conteo__item{{display:flex;flex-direction:column;align-items:center;min-width:64px;}}
  .conteo__num{{font-size:1.25rem;font-weight:700;font-family:ui-monospace,monospace;}}
  .conteo__etq{{font-size:.7rem;color:var(--texto-2);text-transform:uppercase;letter-spacing:.04em;}}
  table.datos{{width:100%;border-collapse:collapse;font-size:.88rem;background:#fff;border:1px solid var(--linea);border-radius:6px;overflow:hidden;}}
  table.datos th, table.datos td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--linea);}}
  table.datos th{{font-size:.72rem;text-transform:uppercase;letter-spacing:.03em;color:var(--texto-2);background:var(--papel);}}
  table.datos tbody tr:last-child td{{border-bottom:none;}}
  .pastilla{{display:inline-block;font-family:ui-monospace,monospace;font-size:.72rem;padding:2px 9px;border-radius:999px;font-weight:600;}}
  .pastilla.warning{{background:var(--alerta-fondo);color:var(--alerta);}}
  .pastilla.error, .pastilla.fatal{{background:var(--riesgo-fondo);color:var(--riesgo);}}
  .pastilla.refactor, .pastilla.convention, .pastilla.info{{background:var(--marca-tenue);color:var(--marca-fuerte);}}
  .vacio{{background:var(--ok-fondo);color:var(--marca-fuerte);padding:22px;border-radius:6px;text-align:center;font-weight:600;}}
  footer{{margin-top:30px;padding-top:16px;border-top:1px solid var(--linea);color:var(--texto-2);font-size:.8rem;}}
  footer code{{background:var(--marca-tenue);padding:1px 6px;border-radius:4px;}}
</style>
</head>
<body>
<div class="envoltura">
  <header>
    <div class="eyebrow">Kardex · Unidad 3 · Verificación (análisis estático)</div>
    <h1>{html.escape(titulo)}</h1>
    <div class="meta">Generado el {ahora} · umbral mínimo del brief: {UMBRAL_MINIMO}/10</div>
  </header>

  <div class="panel">
    <div class="score {clase_score}">
      <div class="num">{puntaje:.2f}</div>
      <div class="etq">/ 10</div>
    </div>
    <div class="conteos">{filas_conteo}</div>
  </div>

  {tabla_html}

  <footer>
    Comando ejecutado: <code>{html.escape(comando)}</code>
  </footer>
</div>
</body>
</html>"""


def principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rutas", nargs="+", help="Archivos o carpetas a analizar")
    parser.add_argument("--salida", required=True, help="Archivo HTML de salida")
    parser.add_argument("--titulo", default="Reporte de Pylint", help="Título del reporte")
    args = parser.parse_args()

    reporte = correr_pylint(args.rutas)
    contenido = construir_html(reporte, args.rutas, args.titulo)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(contenido, encoding="utf-8")

    puntaje = reporte.get("statistics", {}).get("score", 0.0) or 0.0
    print(f"Reporte generado en {salida} (puntaje: {puntaje:.2f}/10)")


if __name__ == "__main__":
    principal()
