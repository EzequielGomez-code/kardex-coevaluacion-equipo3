"""Genera un reporte HTML legible a partir de una corrida de pytest.

Corre pytest pidiéndole un resultado en formato JUnit XML (algo que pytest
ya sabe hacer por su cuenta, sin plugins adicionales) y arma con eso una
página HTML autocontenida: sin JavaScript y sin conexión a internet, para
que abra bien con solo hacer doble clic o con ``start``, en cualquier
computadora que solo tenga Python y pytest instalados.

Uso:
    python generar_reporte_pytest.py <ruta> [<ruta> ...] --salida archivo.html [--titulo "texto"]

Ejemplo real de este proyecto:
    python evidencias/vv/demo_clase/generar_reporte_pytest.py pruebas apps ^
        --salida evidencias/vv/demo_clase/reporte_pytest_v01.html ^
        --titulo "v01 - bateria real"
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def correr_pytest(rutas: list[str]) -> ET.Element:
    """Ejecuta pytest sobre las rutas dadas y devuelve el XML de resultados."""
    with tempfile.TemporaryDirectory() as carpeta_temporal:
        xml_temporal = Path(carpeta_temporal) / "resultado.xml"
        comando = [
            sys.executable, "-m", "pytest", *rutas,
            f"--junitxml={xml_temporal}", "-q", "--tb=short", "--color=no",
        ]
        subprocess.run(comando, capture_output=True, text=True, check=False)
        if not xml_temporal.exists():
            print("pytest no generó el archivo de resultados. Revisa la ruta indicada.", file=sys.stderr)
            raise SystemExit(1)
        return ET.parse(xml_temporal).getroot()


def clase_resultado(conteo_fallidas: int, conteo_errores: int) -> str:
    if conteo_fallidas or conteo_errores:
        return "riesgo"
    return "ok"


def fila_prueba(caso: ET.Element) -> str:
    nombre = caso.get("name", "")
    duracion = float(caso.get("time", "0"))
    fallo = caso.find("failure")
    error = caso.find("error")
    omitida = caso.find("skipped")

    if fallo is not None:
        pastilla, mensaje = "riesgo", fallo.get("message", "").splitlines()[0]
    elif error is not None:
        pastilla, mensaje = "riesgo", error.get("message", "").splitlines()[0]
    elif omitida is not None:
        pastilla, mensaje = "alerta", omitida.get("message", "Omitida")
    else:
        pastilla, mensaje = "ok", ""

    etiqueta = {"ok": "Pasó", "riesgo": "Falló", "alerta": "Omitida"}[pastilla]
    return f"""
      <tr>
        <td><span class="pastilla {pastilla}">{etiqueta}</span></td>
        <td class="mono">{html.escape(nombre)}</td>
        <td class="mono">{duracion * 1000:.0f} ms</td>
        <td>{html.escape(mensaje)}</td>
      </tr>"""


def construir_html(raiz: ET.Element, rutas: list[str], titulo: str) -> str:
    suite = raiz.find("testsuite")
    total = int(suite.get("tests", "0"))
    fallidas = int(suite.get("failures", "0"))
    errores = int(suite.get("errors", "0"))
    omitidas = int(suite.get("skipped", "0"))
    aprobadas = total - fallidas - errores - omitidas
    duracion_total = float(suite.get("time", "0"))
    ahora = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    comando = "pytest " + " ".join(rutas)
    clase_general = clase_resultado(fallidas, errores)

    casos = suite.findall("testcase")
    filas = "".join(fila_prueba(c) for c in casos)

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
  .pastilla.ok{{background:var(--ok-fondo);color:var(--marca-fuerte);}}
  .pastilla.riesgo{{background:var(--riesgo-fondo);color:var(--riesgo);}}
  .pastilla.alerta{{background:var(--alerta-fondo);color:var(--alerta);}}
  footer{{margin-top:30px;padding-top:16px;border-top:1px solid var(--linea);color:var(--texto-2);font-size:.8rem;}}
  footer code{{background:var(--marca-tenue);padding:1px 6px;border-radius:4px;}}
</style>
</head>
<body>
<div class="envoltura">
  <header>
    <div class="eyebrow">Kardex · Unidad 3 · Validación (pruebas automatizadas)</div>
    <h1>{html.escape(titulo)}</h1>
    <div class="meta">Generado el {ahora} · duración total: {duracion_total:.2f} s</div>
  </header>

  <div class="panel">
    <div class="score {clase_general}">
      <div class="num">{aprobadas}/{total}</div>
      <div class="etq">pruebas en verde</div>
    </div>
    <div class="conteos">
      <div class="conteo__item"><span class="conteo__num">{aprobadas}</span><span class="conteo__etq">Pasaron</span></div>
      <div class="conteo__item"><span class="conteo__num">{fallidas}</span><span class="conteo__etq">Fallaron</span></div>
      <div class="conteo__item"><span class="conteo__num">{errores}</span><span class="conteo__etq">Errores</span></div>
      <div class="conteo__item"><span class="conteo__num">{omitidas}</span><span class="conteo__etq">Omitidas</span></div>
    </div>
  </div>

  <table class="datos">
    <thead><tr><th>Resultado</th><th>Prueba</th><th>Duración</th><th>Detalle</th></tr></thead>
    <tbody>{filas}</tbody>
  </table>

  <footer>
    Comando ejecutado: <code>{html.escape(comando)}</code>
  </footer>
</div>
</body>
</html>"""


def principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rutas", nargs="+", help="Archivos o carpetas de pruebas a correr")
    parser.add_argument("--salida", required=True, help="Archivo HTML de salida")
    parser.add_argument("--titulo", default="Reporte de pytest", help="Título del reporte")
    args = parser.parse_args()

    raiz = correr_pytest(args.rutas)
    contenido = construir_html(raiz, args.rutas, args.titulo)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(contenido, encoding="utf-8")

    suite = raiz.find("testsuite")
    print(
        f"Reporte generado en {salida} "
        f"({suite.get('tests')} pruebas, {suite.get('failures')} fallidas)"
    )


if __name__ == "__main__":
    principal()
