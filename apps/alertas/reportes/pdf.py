"""
Constructor único de reportes en PDF.

Un solo generador para los cuatro reportes — membrete, filtros aplicados,
tabla con encabezado que se repite en cada página y pie «Página X de Y» —
así los cuatro tienen la misma cara en vez de reinventar el documento cada
vez. Todo se arma en memoria (``io.BytesIO``): el sistema de archivos de
Render es efímero.
"""

from __future__ import annotations

import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

COLOR_ACENTO = colors.HexColor("#1F5B4E")
COLOR_TEXTO = colors.HexColor("#23211E")
COLOR_TEXTO_SUAVE = colors.HexColor("#6A665F")
COLOR_BORDE = colors.HexColor("#DCD9D1")
COLOR_SUPERFICIE_ALT = colors.HexColor("#FAF9F6")

_ESTILOS = getSampleStyleSheet()
ESTILO_MEMBRETE = ParagraphStyle(
    "Membrete", parent=_ESTILOS["Normal"], textColor=COLOR_TEXTO_SUAVE, fontSize=9, alignment=TA_LEFT,
)
ESTILO_TITULO = ParagraphStyle(
    "TituloReporte", parent=_ESTILOS["Heading1"], textColor=COLOR_TEXTO, fontSize=16,
    spaceBefore=2, spaceAfter=2, alignment=TA_LEFT,
)
ESTILO_FILTROS = ParagraphStyle(
    "Filtros", parent=_ESTILOS["Normal"], textColor=COLOR_TEXTO_SUAVE, fontSize=8, spaceAfter=10,
)


class _CanvasNumerado(Canvas):  # pylint: disable=abstract-method
    """
    Canvas que primero cuenta cuántas páginas tiene el documento y luego las
    dibuja, para poder escribir «Página X de Y» — el total no se sabe hasta
    haber terminado de componer todo el contenido.

    ``Canvas`` declara métodos de anotación (``inkAnnotation``…) que ReportLab
    nunca implementa en la propia clase base tampoco; no hace falta
    sobrescribirlos para que este canvas funcione.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas_guardadas: list[dict] = []

    def showPage(self) -> None:
        self._paginas_guardadas.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._paginas_guardadas)
        for estado in self._paginas_guardadas:
            self.__dict__.update(estado)
            self._dibujar_pie(total)
            super().showPage()
        super().save()

    def _dibujar_pie(self, total: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXTO_SUAVE)
        ancho_pagina = self._pagesize[0]
        texto = f"Página {self._pageNumber} de {total} · Kardex · Ferretería M y F, S.R.L."
        self.drawRightString(ancho_pagina - 16 * mm, 12 * mm, texto)
        self.restoreState()


def construir_pdf(
    titulo: str, filtros_aplicados: list[str], encabezados: list[str], filas: list[list[str]],
    anchos_columnas: list[float] | None = None,
) -> bytes:
    """
    Arma un PDF con membrete, filtros, tabla y pie de página.

    :param filtros_aplicados: frases ya redactadas («Almacén: ALM-01»), no
        pares clave-valor — la vista decide cómo se leen.
    """
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=letter, topMargin=16 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm, title=titulo,
    )

    generado = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    pie_filtros = f" · {' · '.join(filtros_aplicados)}" if filtros_aplicados else ""
    elementos = [
        Paragraph("Kardex — Ferretería M y F, S.R.L.", ESTILO_MEMBRETE),
        Paragraph(titulo, ESTILO_TITULO),
        Paragraph(f"Generado el {generado}{pie_filtros}", ESTILO_FILTROS),
        Spacer(1, 6),
    ]

    if filas:
        tabla = LongTable([encabezados] + filas, colWidths=anchos_columnas, repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACENTO),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_SUPERFICIE_ALT]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        elementos.append(tabla)
    else:
        elementos.append(Paragraph("No hay datos para los filtros elegidos.", ESTILO_FILTROS))

    documento.build(elementos, canvasmaker=_CanvasNumerado)
    return buffer.getvalue()
