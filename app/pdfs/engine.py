"""PDF generation engine — A4 landscape, two A5 halves (ORIGINAL + CÓPIA).

Layout:
  • A4 landscape page split vertically into two A5 portrait halves
  • Left  half = ORIGINAL (fica com o paciente)
  • Right half = CÓPIA    (fica com o médico)
  • Teal label strip at top of each half + dashed cut-line in the middle
  • Teal footer bar at bottom of each half with page numbers
  • Font: DejaVu Sans (≈ Segoe UI), registered as 'SegoeUI'
"""
import os
import io
from datetime import date

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, KeepTogether,
)
from reportlab.platypus.flowables import KeepInFrame
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ─── Font registration (DejaVu Sans ≈ Segoe UI) ──────────────────────────────
_FONT_DIR = '/usr/share/fonts/truetype/dejavu'
_REG  = os.path.join(_FONT_DIR, 'DejaVuSans.ttf')
_BOLD = os.path.join(_FONT_DIR, 'DejaVuSans-Bold.ttf')
_FONTS_OK = False
try:
    if os.path.isfile(_REG) and os.path.isfile(_BOLD):
        pdfmetrics.registerFont(TTFont('SegoeUI',      _REG))
        pdfmetrics.registerFont(TTFont('SegoeUI-Bold', _BOLD))
        _FONTS_OK = True
except Exception:
    pass

F_REG  = 'SegoeUI'      if _FONTS_OK else 'Helvetica'
F_BOLD = 'SegoeUI-Bold' if _FONTS_OK else 'Helvetica-Bold'

# ─── Page geometry ────────────────────────────────────────────────────────────
PAGE    = landscape(A4)        # 841.89 × 595.28 pt  (297 × 210 mm)
A5_W    = PAGE[0] / 2          # 420.94 pt (one A5 portrait width)
A5_H    = PAGE[1]              # 595.28 pt
LABEL_H = 7  * mm              # "ORIGINAL / CÓPIA" strip at top
FOOT_H  = 9  * mm              # teal footer bar at bottom
SIDE_M  = 9  * mm              # left/right margin within each A5 half
GAP_V   = 3  * mm              # gap below label strip and above footer bar
FRAME_W = A5_W - 2 * SIDE_M   # usable content width per A5 half
CONT_H  = PAGE[1] - LABEL_H - FOOT_H   # full vertical content band
KIF_H   = CONT_H - 2 * GAP_V           # KeepInFrame height (with v-gap)

# ─── Palette ──────────────────────────────────────────────────────────────────
TEAL       = colors.HexColor('#14b8a6')
TEAL_DARK  = colors.HexColor('#0d9488')
TEAL_LIGHT = colors.HexColor('#ccfbf1')
COPY_CLR   = colors.HexColor('#0f766e')   # right-half (CÓPIA) label bg
NAVY       = colors.HexColor('#0f172a')
DARK       = colors.HexColor('#1e293b')
GREY       = colors.HexColor('#64748b')
GREY_MID   = colors.HexColor('#94a3b8')
BORDER     = colors.HexColor('#e2e8f0')
ROW_ALT    = colors.HexColor('#f8fafc')
HDR_BG     = colors.HexColor('#0d9488')
WHITE      = colors.white
SECTION_BG = colors.HexColor('#f0fdfa')
STAMP_BG   = colors.HexColor('#e8edf2')
CUT_CLR    = colors.HexColor('#94a3b8')

# ─── i18n defaults ───────────────────────────────────────────────────────────
_DEFAULTS = {
    'treatment_plan': {
        'title':      {'pt': 'PLANO DE TRATAMENTO', 'en': 'TREATMENT PLAN', 'es': 'PLAN DE TRATAMIENTO'},
        'session':    {'pt': 'Sessão', 'en': 'Session', 'es': 'Sesión'},
        'date':       {'pt': 'Data', 'en': 'Date', 'es': 'Fecha'},
        'patient':    {'pt': 'Paciente', 'en': 'Patient', 'es': 'Paciente'},
        'dentist':    {'pt': 'Médico Dentista', 'en': 'Dentist', 'es': 'Dentista'},
        'diagnosis':  {'pt': 'Diagnóstico', 'en': 'Diagnosis', 'es': 'Diagnóstico'},
        'notes':      {'pt': 'Notas Clínicas', 'en': 'Clinical Notes', 'es': 'Notas Clínicas'},
        'plan':       {'pt': 'Plano de Tratamento', 'en': 'Treatment Plan', 'es': 'Plan de Tratamiento'},
        'procedures': {'pt': 'Procedimentos Realizados', 'en': 'Procedures Performed', 'es': 'Procedimientos Realizados'},
        'procedure':  {'pt': 'Procedimento', 'en': 'Procedure', 'es': 'Procedimiento'},
        'qty':        {'pt': 'Qtd.', 'en': 'Qty', 'es': 'Cant.'},
        'price':      {'pt': 'Valor (Kz)', 'en': 'Price (Kz)', 'es': 'Precio (Kz)'},
        'total_label':{'pt': 'Total:', 'en': 'Total:', 'es': 'Total:'},
        'sig':        {'pt': 'Assinatura do Médico Dentista', 'en': 'Dentist Signature', 'es': 'Firma del Dentista'},
        'footer':     {'pt': 'Documento clínico — uso confidencial', 'en': 'Clinical document — confidential', 'es': 'Documento clínico — uso confidencial'},
        'original':   {'pt': 'ORIGINAL — Para o Paciente', 'en': 'ORIGINAL — Patient Copy', 'es': 'ORIGINAL — Para el Paciente'},
        'copy':       {'pt': 'CÓPIA — Para o Médico', 'en': 'COPY — Doctor Copy', 'es': 'COPIA — Para el Médico'},
    },
    'consent_form': {
        'title':      {'pt': 'CONSENTIMENTO INFORMADO', 'en': 'INFORMED CONSENT', 'es': 'CONSENTIMIENTO INFORMADO'},
        'session':    {'pt': 'Sessão', 'en': 'Session', 'es': 'Sesión'},
        'date':       {'pt': 'Data', 'en': 'Date', 'es': 'Fecha'},
        'patient':    {'pt': 'Paciente', 'en': 'Patient', 'es': 'Paciente'},
        'dentist':    {'pt': 'Médico Dentista', 'en': 'Dentist', 'es': 'Dentista'},
        'plan':       {'pt': 'Plano de Tratamento', 'en': 'Treatment Plan', 'es': 'Plan de Tratamiento'},
        'intro': {
            'pt': ('Eu, abaixo assinado(a), declaro que fui devidamente informado(a) pelo(a) Médico Dentista '
                   'acima identificado(a) sobre o tratamento proposto, seus riscos, benefícios e alternativas. '
                   'Autorizo livremente a realização do tratamento e declaro ter compreendido as explicações prestadas.'),
            'en': ('I, the undersigned, declare that I have been duly informed by the Dentist identified above '
                   'about the proposed treatment, its risks, benefits and alternatives. '
                   'I freely consent to the performance of the treatment and confirm I have understood the explanations given.'),
            'es': ('Yo, el abajo firmante, declaro que he sido debidamente informado(a) por el/la Dentista '
                   'identificado(a) arriba sobre el tratamiento propuesto, sus riesgos, beneficios y alternativas. '
                   'Consiento libremente en la realización del tratamiento y declaro haber comprendido las explicaciones.'),
        },
        'patient_sig':{'pt': 'Assinatura do Paciente', 'en': 'Patient Signature', 'es': 'Firma del Paciente'},
        'dentist_sig':{'pt': 'Assinatura do Médico Dentista', 'en': 'Dentist Signature', 'es': 'Firma del Dentista'},
        'date_place': {'pt': 'Local e Data', 'en': 'Place and Date', 'es': 'Lugar y Fecha'},
        'footer':     {'pt': 'Documento clínico — uso confidencial', 'en': 'Clinical document — confidential', 'es': 'Documento clínico — uso confidencial'},
        'original':   {'pt': 'ORIGINAL — Para o Paciente', 'en': 'ORIGINAL — Patient Copy', 'es': 'ORIGINAL — Para el Paciente'},
        'copy':       {'pt': 'CÓPIA — Para o Médico', 'en': 'COPY — Doctor Copy', 'es': 'COPIA — Para el Médico'},
    },
    'prescription': {
        'title':       {'pt': 'RECEITA MÉDICA', 'en': 'MEDICAL PRESCRIPTION', 'es': 'RECETA MÉDICA'},
        'session':     {'pt': 'Sessão', 'en': 'Session', 'es': 'Sesión'},
        'date':        {'pt': 'Data', 'en': 'Date', 'es': 'Fecha'},
        'patient':     {'pt': 'Paciente', 'en': 'Patient', 'es': 'Paciente'},
        'dentist':     {'pt': 'Médico Dentista', 'en': 'Dentist', 'es': 'Dentista'},
        'medicine':    {'pt': 'Medicamento', 'en': 'Medicine', 'es': 'Medicamento'},
        'dosage':      {'pt': 'Dosagem', 'en': 'Dosage', 'es': 'Dosis'},
        'frequency':   {'pt': 'Frequência', 'en': 'Frequency', 'es': 'Frecuencia'},
        'duration':    {'pt': 'Duração', 'en': 'Duration', 'es': 'Duración'},
        'instructions':{'pt': 'Instruções', 'en': 'Instructions', 'es': 'Instrucciones'},
        'section_rp':  {'pt': 'Rp.', 'en': 'Rx.', 'es': 'Rp.'},
        'sig':         {'pt': 'Assinatura e Carimbo', 'en': 'Signature & Stamp', 'es': 'Firma y Sello'},
        'validity':    {'pt': 'Válido por 30 dias a partir da data de emissão.', 'en': 'Valid for 30 days from issue date.', 'es': 'Válido por 30 días desde la fecha de emisión.'},
        'footer':      {'pt': 'Documento clínico — uso confidencial', 'en': 'Clinical document — confidential', 'es': 'Documento clínico — uso confidencial'},
        'original':    {'pt': 'ORIGINAL — Para o Paciente', 'en': 'ORIGINAL — Patient Copy', 'es': 'ORIGINAL — Para el Paciente'},
        'copy':        {'pt': 'CÓPIA — Para o Médico', 'en': 'COPY — Doctor Copy', 'es': 'COPIA — Para el Médico'},
    },
}


def _s(field, locale, settings, type_name):
    key = f'pdf_{type_name}_{field}_{locale}'
    val = settings.get(key, '')
    if val:
        return val
    d = _DEFAULTS.get(type_name, {}).get(field, {})
    if isinstance(d, dict):
        return d.get(locale, d.get('pt', field))
    return str(d)


def _load_settings():
    try:
        from ..models import AppSetting
        return AppSetting.all_as_dict()
    except Exception:
        return {}


def _accent(settings, type_name):
    val = settings.get(f'pdf_{type_name}_accent_color', '')
    if val and val.startswith('#') and len(val) in (4, 7):
        try:
            return colors.HexColor(val)
        except Exception:
            pass
    return TEAL


def _show_logo(settings, type_name):
    return settings.get(f'pdf_{type_name}_show_logo', '1') != '0'


def _show_pagenum(settings, type_name):
    return settings.get(f'pdf_{type_name}_show_pagenum', '1') != '0'


def _watermark_text(settings, type_name):
    return settings.get(f'pdf_{type_name}_watermark_text', '').strip()


# ─── Styles ───────────────────────────────────────────────────────────────────

def _styles(accent=None):
    if accent is None:
        accent = TEAL
    return {
        'doc_title':    ParagraphStyle('DocTitle',
            fontName=F_BOLD, fontSize=12, textColor=WHITE,
            alignment=TA_CENTER, leading=15, spaceAfter=0, spaceBefore=0),
        'clinic_name':  ParagraphStyle('ClinicName',
            fontName=F_BOLD, fontSize=12, textColor=WHITE, spaceAfter=2, leading=14),
        'clinic_sub':   ParagraphStyle('ClinicSub',
            fontName=F_REG, fontSize=9, textColor=colors.HexColor('#a7f3d0'), spaceAfter=1),
        'clinic_contact': ParagraphStyle('ClinicContact',
            fontName=F_REG, fontSize=7.5, textColor=colors.HexColor('#99f6e4')),
        'section':      ParagraphStyle('Section',
            fontName=F_BOLD, fontSize=10, textColor=WHITE, alignment=TA_LEFT),
        'body':         ParagraphStyle('Body',
            fontName=F_REG, fontSize=9.5, textColor=DARK, leading=14),
        'body_j':       ParagraphStyle('BodyJ',
            fontName=F_REG, fontSize=9.5, textColor=DARK, leading=14, alignment=TA_JUSTIFY),
        'label':        ParagraphStyle('Label',
            fontName=F_BOLD, fontSize=8.5, textColor=GREY),
        'label_val':    ParagraphStyle('LabelVal',
            fontName=F_REG, fontSize=9.5, textColor=DARK),
        'sig_name':     ParagraphStyle('SigName',
            fontName=F_BOLD, fontSize=8.5, textColor=DARK, alignment=TA_CENTER, spaceAfter=1),
        'sig_label':    ParagraphStyle('SigLabel',
            fontName=F_REG, fontSize=7.5, textColor=GREY, alignment=TA_CENTER),
        'tbl_hdr':      ParagraphStyle('TblHdr',
            fontName=F_BOLD, fontSize=8.5, textColor=WHITE),
        'tbl_body':     ParagraphStyle('TblBody',
            fontName=F_REG, fontSize=8.5, textColor=DARK),
        'small':        ParagraphStyle('Small',
            fontName=F_REG, fontSize=7.5, textColor=GREY),
        'small_c':      ParagraphStyle('SmallC',
            fontName=F_REG, fontSize=7.5, textColor=GREY_MID, alignment=TA_CENTER),
        'total':        ParagraphStyle('Total',
            fontName=F_BOLD, fontSize=9, textColor=DARK, alignment=TA_RIGHT),
        'total_val':    ParagraphStyle('TotalVal',
            fontName=F_BOLD, fontSize=10, textColor=accent, alignment=TA_RIGHT),
        'rp_big':       ParagraphStyle('RpBig',
            fontName=F_BOLD, fontSize=22, textColor=colors.HexColor('#d1fae5'),
            alignment=TA_CENTER),
        'validity':     ParagraphStyle('Validity',
            fontName=F_REG, fontSize=7, textColor=GREY, alignment=TA_CENTER),
        'footer_l':     ParagraphStyle('FooterL',
            fontName=F_REG, fontSize=6.5, textColor=colors.HexColor('#a7f3d0')),
        'footer_r':     ParagraphStyle('FooterR',
            fontName=F_REG, fontSize=6.5, textColor=WHITE, alignment=TA_RIGHT),
    }


# ─── Canvas: draws labels, cut-line, and footer bars on every page ────────────

def _make_canvas_class(show_pn=True, accent_color=None, watermark='',
                        lbl_original='ORIGINAL — Para o Paciente',
                        lbl_copy='CÓPIA — Para o Médico',
                        footer_text=''):
    if accent_color is None:
        accent_color = TEAL
    _wm = watermark

    class _DualA5Canvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            rl_canvas.Canvas.__init__(self, *a, **kw)
            self._page_states = []

        def showPage(self):
            self._page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._page_states)
            for state in self._page_states:
                self.__dict__.update(state)
                if _wm:
                    self._draw_watermark(_wm)
                self._draw_chrome(total)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

        def _draw_chrome(self, total):
            self.saveState()
            W, H = PAGE

            # ── Label strips at the top ──────────────────────────────────────
            # Left = ORIGINAL (teal)
            self.setFillColor(accent_color)
            self.rect(0, H - LABEL_H, A5_W, LABEL_H, fill=1, stroke=0)
            # Right = CÓPIA (darker teal)
            self.setFillColor(COPY_CLR)
            self.rect(A5_W, H - LABEL_H, A5_W, LABEL_H, fill=1, stroke=0)

            # Scissors + label text
            self.setFont(F_BOLD if _FONTS_OK else 'Helvetica-Bold', 7)
            self.setFillColor(WHITE)
            self.drawString(SIDE_M, H - LABEL_H + 2.2 * mm,
                            '\u2702  ' + lbl_original)
            self.drawRightString(W - SIDE_M, H - LABEL_H + 2.2 * mm,
                                 lbl_copy + '  \u2702')

            # ── Dashed vertical cut-line ──────────────────────────────────────
            self.setStrokeColor(CUT_CLR)
            self.setLineWidth(0.6)
            self.setDash(5, 4)
            self.line(A5_W, 0, A5_W, H)
            self.setDash()  # reset

            # ── Footer bars (teal, full width, bottom) ────────────────────────
            # Left footer
            self.setFillColor(accent_color)
            self.rect(0, 0, A5_W, FOOT_H, fill=1, stroke=0)
            # Right footer
            self.setFillColor(COPY_CLR)
            self.rect(A5_W, 0, A5_W, FOOT_H, fill=1, stroke=0)

            # Footer text left halves
            fn_reg = F_REG if _FONTS_OK else 'Helvetica'
            fn_bld = F_BOLD if _FONTS_OK else 'Helvetica-Bold'
            self.setFont(fn_reg, 6.5)
            self.setFillColor(colors.HexColor('#a7f3d0'))
            if footer_text:
                self.drawString(SIDE_M, 2.6 * mm, footer_text)
                self.drawString(A5_W + SIDE_M, 2.6 * mm, footer_text)

            # Page numbers (right side of each half)
            if show_pn and total > 0:
                self.setFont(fn_bld, 7)
                self.setFillColor(WHITE)
                pn = f'{self._pageNumber} / {total}'
                self.drawRightString(A5_W - SIDE_M, 2.6 * mm, pn)
                self.drawRightString(W - SIDE_M,    2.6 * mm, pn)

            self.restoreState()

        def _draw_watermark(self, text):
            self.saveState()
            W, H = PAGE
            self.setFont(F_BOLD if _FONTS_OK else 'Helvetica-Bold', 44)
            self.setFillColor(colors.Color(0.92, 0.92, 0.92))
            # Left half
            self.translate(A5_W / 2, H / 2)
            self.rotate(40)
            self.drawCentredString(0, 0, text)
            self.restoreState()
            self.saveState()
            # Right half
            self.setFont(F_BOLD if _FONTS_OK else 'Helvetica-Bold', 44)
            self.setFillColor(colors.Color(0.92, 0.92, 0.92))
            self.translate(A5_W + A5_W / 2, H / 2)
            self.rotate(40)
            self.drawCentredString(0, 0, text)
            self.restoreState()

    return _DualA5Canvas


# ─── Shared layout helpers ────────────────────────────────────────────────────

def _section_hdr(text, st, W, accent):
    """Left-accent strip + teal-tinted bg section header with enhanced styling."""
    strip = Table([['']], colWidths=[5 * mm])
    strip.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), accent),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    label = Table([[Paragraph(text.upper(), st['section'])]], colWidths=[W - 5 * mm])
    label.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), accent),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
    ]))
    wrapper = Table([[strip, label]], colWidths=[5 * mm, W - 5 * mm])
    wrapper.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('VALIGN',       (0, 0), (-1, -1), 'STRETCH'),
    ]))
    return wrapper


def _info_box(rows, st, col_widths):
    """Clean label/value grid with alternating rows and border box."""
    data = [[Paragraph(lbl, st['label']),
             Paragraph(str(val or '—'), st['label_val'])] for lbl, val in rows]
    cmds = [
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW',    (0, 0), (-1, -1), 0.6, BORDER),
        ('BOX',          (0, 0), (-1, -1), 0.8, TEAL_DARK),
    ]
    for i in range(len(rows)):
        cmds.append(('BACKGROUND', (0, i), (-1, i),
                     ROW_ALT if i % 2 == 0 else WHITE))
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(cmds))
    return t


def _sig_block(sig_path, name, label, st, width=50 * mm, license_number=None, show_label=True):
    items = []
    if sig_path and os.path.isfile(sig_path):
        try:
            items.append(Image(sig_path, width=width - 4 * mm, height=14 * mm))
        except Exception:
            items.append(Spacer(1, 16 * mm))
    else:
        items.append(Spacer(1, 16 * mm))
    items.append(HRFlowable(width=width, thickness=0.7, color=GREY_MID,
                             dash=(2, 3), spaceBefore=2, spaceAfter=3))
    items.append(Paragraph(name, st['sig_name']))
    if license_number:
        items.append(Paragraph(license_number, st['sig_label']))
    if show_label:
        items.append(Paragraph(label, st['sig_label']))
    return items


def _header_table(st, W, locale, settings, upload_folder, type_name, acc, doc_title):
    """Full-width teal banner: logo+clinic info left | doc title right."""
    def _gs(f):
        return settings.get(f'pdf_{type_name}_clinic_{f}', '') or ''

    app_name   = _gs('name') or settings.get('app_clinic_name', '') or settings.get('app_name', 'DentClinic')
    sub_defs   = {'pt': 'Clínica Odontológica', 'en': 'Dental Clinic', 'es': 'Clínica Odontológica'}
    clinic_sub = _gs('subtitle') or settings.get('app_subtitle', '') or sub_defs.get(locale, 'Clínica Odontológica')
    _addr  = _gs('address') or settings.get('app_address', '')
    _phone = _gs('phone')   or settings.get('app_phone', '')
    _email = _gs('email')   or settings.get('app_email', '')
    _nif   = _gs('nif')     or settings.get('app_nif', '')
    contact_parts = [p for p in [_addr, _phone, _email,
                                   (f"NIF: {_nif}" if _nif else '')] if p]
    contact_line = '  ·  '.join(contact_parts)

    logo_img = None
    if upload_folder and _show_logo(settings, type_name):
        logo_file = settings.get('app_logo', '')
        if logo_file:
            logo_path = os.path.join(upload_folder, 'logos', logo_file)
            if os.path.isfile(logo_path):
                ext = os.path.splitext(logo_file)[1].lower()
                if ext in ('.svg',):
                    logo_img = None  # SVG not supported by ReportLab/PIL
                else:
                    try:
                        logo_img = Image(logo_path, width=45 * mm, height=28 * mm)
                        logo_img.hAlign = 'LEFT'
                    except Exception:
                        logo_img = None

    left_items = []
    if logo_img:
        left_items.append(logo_img)
        left_items.append(Spacer(1, 2 * mm))
    left_items.append(Paragraph(app_name, st['clinic_name']))
    left_items.append(Paragraph(clinic_sub, st['clinic_sub']))
    if contact_line:
        left_items.append(Spacer(1, 1 * mm))
        left_items.append(Paragraph(contact_line, st['clinic_contact']))

    left_t = Table([[item] for item in left_items], colWidths=[W * 0.60])
    left_t.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 1),
    ]))

    right_t = Table([[Paragraph(doc_title, st['doc_title'])]], colWidths=[W * 0.34])
    right_t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), colors.HexColor('#0f766e')),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    outer = Table([[left_t, right_t]], colWidths=[W * 0.62, W * 0.38])
    outer.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), acc),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 5 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
        ('TOPPADDING',   (0, 0), (-1, -1), 5 * mm),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5 * mm),
    ]))
    return outer


def _footer_rule(st, W, footer_text):
    """Thin grey rule + footer/date row above the teal footer bar."""
    story = []
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER,
                             spaceBefore=0, spaceAfter=2))
    today = date.today().strftime('%d/%m/%Y')
    ft = Table([[Paragraph(footer_text or '', st['footer_l']),
                 Paragraph(today, st['footer_r'])]], colWidths=[W * 0.7, W * 0.3])
    ft.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    story.append(ft)
    return story


# ─── Single-frame doc + two-up table helper ───────────────────────────────────
# Using ONE frame across the full A4 content band ensures both halves always
# land on the same page — no FrameBreak overflow issues.

def _make_doc(buf):
    """A4 landscape, single frame covering the band between label and footer."""
    frame = Frame(0, FOOT_H, PAGE[0], CONT_H,
                  id='main',
                  topPadding=0, bottomPadding=0, leftPadding=0, rightPadding=0)
    template = PageTemplate(id='TwoUp', frames=[frame])
    doc = BaseDocTemplate(buf, pagesize=PAGE,
                          leftMargin=0, rightMargin=0,
                          topMargin=0, bottomMargin=0,
                          pageTemplates=[template])
    return doc


def _build_two_up(story_left, story_right):
    """Wrap two identical stories side-by-side in a KeepInFrame Table.

    Both halves are placed in a single Table row so ReportLab never splits
    them across pages.  Content is shrunk (not truncated) if it overflows.
    """
    kif_l = KeepInFrame(FRAME_W, KIF_H, story_left,  mode='shrink')
    kif_r = KeepInFrame(FRAME_W, KIF_H, story_right, mode='shrink')
    tbl = Table(
        [[kif_l, kif_r]],
        colWidths=[A5_W, A5_W],
    )
    tbl.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), SIDE_M),
        ('RIGHTPADDING', (0, 0), (-1, -1), SIDE_M),
        ('TOPPADDING',   (0, 0), (-1, -1), GAP_V),
        ('BOTTOMPADDING',(0, 0), (-1, -1), GAP_V),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
    ]))
    return [tbl]


# ─── Treatment Plan ───────────────────────────────────────────────────────────

def _story_treatment_plan(session, locale, settings, TN, st, acc, W, upload_folder,
                           treatments):
    story = []
    doc_title = _s('title', locale, settings, TN)
    story.append(_header_table(st, W, locale, settings, upload_folder, TN, acc, doc_title))
    story.append(Spacer(1, 3 * mm))

    patient   = session.patient
    dentist   = session.dentist
    sess_date = session.session_date.strftime('%d/%m/%Y') if session.session_date else '—'

    story.append(_section_hdr(
        f"{_s('session', locale, settings, TN)} / {_s('patient', locale, settings, TN)}",
        st, W, acc))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_info_box([
        (_s('patient', locale, settings, TN) + ':', patient.full_name if patient else '—'),
        (_s('dentist', locale, settings, TN) + ':', dentist.full_name if dentist else '—'),
        (_s('session', locale, settings, TN) + ':', session.session_code),
        (_s('date',    locale, settings, TN) + ':', sess_date),
    ], st, [W * 0.30, W * 0.70]))
    story.append(Spacer(1, 3 * mm))

    if session.diagnosis:
        story.append(_section_hdr(_s('diagnosis', locale, settings, TN), st, W, acc))
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(session.diagnosis, st['body_j']))
        story.append(Spacer(1, 3 * mm))

    if session.clinical_notes:
        story.append(_section_hdr(_s('notes', locale, settings, TN), st, W, acc))
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(session.clinical_notes, st['body_j']))
        story.append(Spacer(1, 3 * mm))

    if session.treatment_plan:
        story.append(_section_hdr(_s('plan', locale, settings, TN), st, W, acc))
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(session.treatment_plan, st['body_j']))
        story.append(Spacer(1, 3 * mm))

    if treatments:
        story.append(_section_hdr(_s('procedures', locale, settings, TN), st, W, acc))
        story.append(Spacer(1, 1.5 * mm))

        cw  = [W * 0.50, W * 0.10, W * 0.22, W * 0.18]
        hdr = [Paragraph(_s('procedure', locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('qty',       locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('price',     locale, settings, TN), st['tbl_hdr']),
               Paragraph('',                                    st['tbl_hdr'])]
        data  = [hdr]
        total = 0.0
        for tmt in treatments:
            name  = tmt.treatment.name_for_locale(locale) if tmt.treatment else '—'
            price = float(tmt.price_at_time or
                          (tmt.treatment.price if tmt.treatment else 0) or 0)
            qty   = tmt.quantity or 1
            total += price * qty
            data.append([Paragraph(name,          st['tbl_body']),
                         Paragraph(str(qty),       st['tbl_body']),
                         Paragraph(f'{price:,.2f}',st['tbl_body']),
                         Paragraph('',             st['tbl_body'])])
        tl = _s('total_label', locale, settings, TN)
        data.append([Paragraph('', st['tbl_hdr']),
                     Paragraph('', st['tbl_hdr']),
                     Paragraph(tl, st['total']),
                     Paragraph(f'{total:,.2f} Kz', st['total_val'])])
        cmds = [
            ('BACKGROUND',    (0, 0), (-1, 0),   HDR_BG),
            ('LINEBELOW',     (0, 0), (-1, 0),   1.5, TEAL_DARK),
            ('BOX',           (0, 0), (-1, -2),  0.5, TEAL_DARK),
            ('GRID',          (0, 1), (-1, -2),  0.4, BORDER),
            ('BACKGROUND',    (0, -1),(-1, -1),  TEAL_LIGHT),
            ('LINEABOVE',     (0, -1),(-1, -1),  1, TEAL_DARK),
            ('SPAN',          (2, -1),(3, -1)),
            ('TOPPADDING',    (0, 0), (-1, -1),  5),
            ('BOTTOMPADDING', (0, 0), (-1, -1),  5),
            ('LEFTPADDING',   (0, 0), (-1, -1),  6),
            ('RIGHTPADDING',  (0, 0), (-1, -1),  6),
            ('VALIGN',        (0, 0), (-1, -1),  'MIDDLE'),
        ]
        for i in range(1, len(data) - 1):
            cmds.append(('BACKGROUND', (0, i), (-1, i),
                          ROW_ALT if i % 2 == 0 else WHITE))
        tbl = Table(data, colWidths=cw)
        tbl.setStyle(TableStyle(cmds))
        story.append(tbl)
        story.append(Spacer(1, 5 * mm))

    # Signature
    sig_path = None
    if dentist and getattr(dentist, 'signature_path', None) and upload_folder:
        sig_path = os.path.join(upload_folder, dentist.signature_path)
    sig_w = W * 0.55
    dentist_ln = getattr(dentist, 'license_number', None) if dentist else None
    show_sig_lbl = settings.get(f'pdf_{TN}_show_sig_label', '1') != '0'
    sig_elems = _sig_block(sig_path, dentist.full_name if dentist else '—',
                            _s('sig', locale, settings, TN), st, sig_w,
                            license_number=dentist_ln, show_label=show_sig_lbl)
    sig_inner = Table([[e] for e in sig_elems], colWidths=[sig_w])
    sig_inner.setStyle(TableStyle([('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
                                    ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                    ('TOPPADDING',   (0, 0), (-1, -1), 0),
                                    ('BOTTOMPADDING',(0, 0), (-1, -1), 0)]))
    story.append(Table([[sig_inner]], colWidths=[W]))
    story.extend(_footer_rule(st, W, _s('footer', locale, settings, TN)))
    return story


def generate_treatment_plan_pdf(session, locale='pt', upload_folder=None,
                                _treatments=None):
    TN = 'treatment_plan'
    settings = _load_settings()
    acc = _accent(settings, TN)
    st  = _styles(acc)
    wm  = _watermark_text(settings, TN)

    from ..models import SessionTreatment
    treatments = _treatments if _treatments is not None else \
                 SessionTreatment.query.filter_by(session_id=session.id).all()

    uf = upload_folder if _show_logo(settings, TN) else None
    s1 = _story_treatment_plan(session, locale, settings, TN, st, acc, FRAME_W, uf, treatments)
    s2 = _story_treatment_plan(session, locale, settings, TN, st, acc, FRAME_W, uf, treatments)

    buf = io.BytesIO()
    doc = _make_doc(buf)
    doc.build(_build_two_up(s1, s2), canvasmaker=_make_canvas_class(
        _show_pagenum(settings, TN), acc, wm,
        lbl_original=_s('original', locale, settings, TN),
        lbl_copy=_s('copy', locale, settings, TN),
        footer_text=_s('footer', locale, settings, TN)))
    buf.seek(0)
    return buf.read()


# ─── Consent Form ─────────────────────────────────────────────────────────────

def _story_consent_form(session, locale, settings, TN, st, acc, W, upload_folder):
    story = []
    doc_title = _s('title', locale, settings, TN)
    story.append(_header_table(st, W, locale, settings, upload_folder, TN, acc, doc_title))
    story.append(Spacer(1, 3 * mm))

    patient   = session.patient
    dentist   = session.dentist
    sess_date = session.session_date.strftime('%d/%m/%Y') if session.session_date else '—'

    story.append(_info_box([
        (_s('patient', locale, settings, TN) + ':', patient.full_name if patient else '—'),
        (_s('dentist', locale, settings, TN) + ':', dentist.full_name if dentist else '—'),
        (_s('session', locale, settings, TN) + ':', session.session_code),
        (_s('date',    locale, settings, TN) + ':', sess_date),
    ], st, [W * 0.30, W * 0.70]))
    story.append(Spacer(1, 4 * mm))

    intro_tbl = Table([[Paragraph(_s('intro', locale, settings, TN), st['body_j'])]],
                       colWidths=[W])
    intro_tbl.setStyle(TableStyle([
        ('BOX',          (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND',   (0, 0), (-1, -1), ROW_ALT),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(intro_tbl)
    story.append(Spacer(1, 4 * mm))

    if session.treatment_plan:
        story.append(_section_hdr(_s('plan', locale, settings, TN), st, W, acc))
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(session.treatment_plan, st['body_j']))
        story.append(Spacer(1, 6 * mm))

    # Dual signatures
    sig_path = None
    if dentist and getattr(dentist, 'signature_path', None) and upload_folder:
        sig_path = os.path.join(upload_folder, dentist.signature_path)
    col_w = W * 0.44

    def _sig_col(elems, cw):
        t = Table([[e] for e in elems], colWidths=[cw])
        t.setStyle(TableStyle([('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
                                ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                ('TOPPADDING',   (0, 0), (-1, -1), 0),
                                ('BOTTOMPADDING',(0, 0), (-1, -1), 0)]))
        return t

    dentist_ln = getattr(dentist, 'license_number', None) if dentist else None
    show_sig_lbl = settings.get(f'pdf_{TN}_show_sig_label', '1') != '0'
    psig = _sig_block(None, patient.full_name if patient else '—',
                      _s('patient_sig', locale, settings, TN), st, col_w,
                      show_label=show_sig_lbl)
    dsig = _sig_block(sig_path, dentist.full_name if dentist else '—',
                      _s('dentist_sig', locale, settings, TN), st, col_w,
                      license_number=dentist_ln, show_label=show_sig_lbl)

    sig_tbl = Table([[_sig_col(psig, col_w), '', _sig_col(dsig, col_w)]],
                     colWidths=[W * 0.45, W * 0.10, W * 0.45])
    sig_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 5 * mm))

    # Date/Place line
    dp = _s('date_place', locale, settings, TN)
    story.append(Table([[Paragraph(f'{dp}:', st['label']),
                          Paragraph('', st['label_val'])]],
                         colWidths=[W * 0.28, W * 0.72]))
    story.append(HRFlowable(width=W * 0.72, thickness=0.5, color=GREY_MID,
                             spaceBefore=1, spaceAfter=0))

    story.extend(_footer_rule(st, W, _s('footer', locale, settings, TN)))
    return story


def generate_consent_form_pdf(session, locale='pt', upload_folder=None,
                              _treatments=None):
    TN = 'consent_form'
    settings = _load_settings()
    acc = _accent(settings, TN)
    st  = _styles(acc)
    wm  = _watermark_text(settings, TN)

    uf = upload_folder if _show_logo(settings, TN) else None
    s1 = _story_consent_form(session, locale, settings, TN, st, acc, FRAME_W, uf)
    s2 = _story_consent_form(session, locale, settings, TN, st, acc, FRAME_W, uf)

    buf = io.BytesIO()
    doc = _make_doc(buf)
    doc.build(_build_two_up(s1, s2), canvasmaker=_make_canvas_class(
        _show_pagenum(settings, TN), acc, wm,
        lbl_original=_s('original', locale, settings, TN),
        lbl_copy=_s('copy', locale, settings, TN),
        footer_text=_s('footer', locale, settings, TN)))
    buf.seek(0)
    return buf.read()


# ─── Prescription ─────────────────────────────────────────────────────────────

def _story_prescription(session, locale, settings, TN, st, acc, W, upload_folder,
                         prescriptions):
    story = []
    doc_title = _s('title', locale, settings, TN)
    story.append(_header_table(st, W, locale, settings, upload_folder, TN, acc, doc_title))
    story.append(Spacer(1, 3 * mm))

    patient   = session.patient
    dentist   = session.dentist
    sess_date = session.session_date.strftime('%d/%m/%Y') if session.session_date else '—'

    story.append(_info_box([
        (_s('patient', locale, settings, TN) + ':', patient.full_name if patient else '—'),
        (_s('dentist', locale, settings, TN) + ':', dentist.full_name if dentist else '—'),
        (_s('date',    locale, settings, TN) + ':', sess_date),
        (_s('session', locale, settings, TN) + ':', session.session_code),
    ], st, [W * 0.30, W * 0.70]))
    story.append(Spacer(1, 3 * mm))

    if prescriptions:
        rp_label = _s('section_rp', locale, settings, TN)
        rp_tbl = Table([[Paragraph(rp_label, st['rp_big']),
                          Paragraph(
                              'Rp. = Recipe — prescrito pelo médico dentista.'
                              if locale == 'pt' else
                              'Rx. = Recipe — prescribed by the dentist.'
                              if locale == 'en' else
                              'Rp. = Recipe — recetado por el dentista.',
                              st['small_c'])]],
                         colWidths=[W * 0.15, W * 0.85])
        rp_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, -1), acc),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',  (0, 0), (0, 0),   4),
            ('RIGHTPADDING', (0, 0), (0, 0),   3),
            ('LEFTPADDING',  (1, 0), (1, 0),   4),
            ('RIGHTPADDING', (1, 0), (1, 0),   6),
            ('TOPPADDING',   (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ]))
        story.append(rp_tbl)
        story.append(Spacer(1, 2 * mm))

        cw = [W * 0.26, W * 0.13, W * 0.16, W * 0.13, W * 0.32]
        hdr = [Paragraph(_s('medicine',     locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('dosage',       locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('frequency',    locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('duration',     locale, settings, TN), st['tbl_hdr']),
               Paragraph(_s('instructions', locale, settings, TN), st['tbl_hdr'])]
        data = [hdr]
        for rx in prescriptions:
            med = rx.medicine.name_for_locale(locale) if rx.medicine else '—'
            data.append([Paragraph(med,                    st['tbl_body']),
                         Paragraph(rx.dosage or '—',       st['tbl_body']),
                         Paragraph(rx.frequency or '—',    st['tbl_body']),
                         Paragraph(rx.duration or '—',     st['tbl_body']),
                         Paragraph(rx.instructions or '—', st['tbl_body'])])
        cmds = [
            ('BACKGROUND',    (0, 0), (-1, 0),  HDR_BG),
            ('LINEBELOW',     (0, 0), (-1, 0),  1.5, TEAL_DARK),
            ('BOX',           (0, 0), (-1, -1), 0.5, TEAL_DARK),
            ('GRID',          (0, 1), (-1, -1), 0.4, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]
        for i in range(1, len(data)):
            cmds.append(('BACKGROUND', (0, i), (-1, i),
                          ROW_ALT if i % 2 == 0 else WHITE))
        tbl = Table(data, colWidths=cw)
        tbl.setStyle(TableStyle(cmds))
        story.append(tbl)
        story.append(Spacer(1, 2 * mm))

        validity_tbl = Table(
            [[Paragraph(_s('validity', locale, settings, TN), st['validity'])]],
            colWidths=[W])
        validity_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, -1), STAMP_BG),
            ('BOX',          (0, 0), (-1, -1), 0.7, TEAL_DARK),
            ('TOPPADDING',   (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
            ('LEFTPADDING',  (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(validity_tbl)
    else:
        story.append(Paragraph('—', st['body']))

    story.append(Spacer(1, 6 * mm))

    sig_path = None
    if dentist and getattr(dentist, 'signature_path', None) and upload_folder:
        sig_path = os.path.join(upload_folder, dentist.signature_path)
    sig_w = W * 0.55
    dentist_ln = getattr(dentist, 'license_number', None) if dentist else None
    show_sig_lbl = settings.get(f'pdf_{TN}_show_sig_label', '1') != '0'
    sig_elems = _sig_block(sig_path, dentist.full_name if dentist else '—',
                            _s('sig', locale, settings, TN), st, sig_w,
                            license_number=dentist_ln, show_label=show_sig_lbl)
    sig_inner = Table([[e] for e in sig_elems], colWidths=[sig_w])
    sig_inner.setStyle(TableStyle([('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
                                    ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                    ('TOPPADDING',   (0, 0), (-1, -1), 0),
                                    ('BOTTOMPADDING',(0, 0), (-1, -1), 0)]))
    story.append(Table([[sig_inner]], colWidths=[W]))
    story.extend(_footer_rule(st, W, _s('footer', locale, settings, TN)))
    return story


def generate_prescription_pdf(session, locale='pt', upload_folder=None,
                              _prescriptions=None):
    TN = 'prescription'
    settings = _load_settings()
    acc = _accent(settings, TN)
    st  = _styles(acc)
    wm  = _watermark_text(settings, TN)

    from ..models import Prescription
    prescriptions = _prescriptions if _prescriptions is not None else \
                    Prescription.query.filter_by(session_id=session.id).all()

    uf = upload_folder if _show_logo(settings, TN) else None
    s1 = _story_prescription(session, locale, settings, TN, st, acc, FRAME_W, uf, prescriptions)
    s2 = _story_prescription(session, locale, settings, TN, st, acc, FRAME_W, uf, prescriptions)

    buf = io.BytesIO()
    doc = _make_doc(buf)
    doc.build(_build_two_up(s1, s2), canvasmaker=_make_canvas_class(
        _show_pagenum(settings, TN), acc, wm,
        lbl_original=_s('original', locale, settings, TN),
        lbl_copy=_s('copy', locale, settings, TN),
        footer_text=_s('footer', locale, settings, TN)))
    buf.seek(0)
    return buf.read()
