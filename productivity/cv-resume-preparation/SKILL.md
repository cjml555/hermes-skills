---
name: cv-resume-preparation
description: Create enhanced, ATS-friendly CVs/resumes with PDF output.
---

# CV/Resume Preparation

## Always-on Rules (User Preferences)

- **Language**: Respond in Spanish (Latin American neutral, no voseo).
- **Tone**: Kawaii — use expressions like (◕‿◕), ★, ♪, ~! Be warm and enthusiastic.
- **CV Standards**: Quantify achievements (+15 clientes, 85% acuerdos, 20% reducción). Use bullet points with metrics.
- **Structure**: Name → Contact → Profile → Education → Experience → Skills → Languages. ATS-friendly sections with clear headers.
- **Output**: Always deliver a print-ready PDF plus a Markdown version with icons for preview.

## Procedure

### Step 1: Extract Text from Input Document

Use `pdftotext` (preferred) or Python `fitz` (PyMuPDF) for PDFs. For DOCX, use `python-docx`.

bash
# Preferred: pdftotext
pdftotext input.pdf - 2>/dev/null

# Fallback: PyMuPDF
python3 -c "import fitz; doc=fitz.open('input.pdf'); [print(p.get_text()) for p in doc]"


### Step 2: Analyze the CV

Identify:
- **Missing sections**: Languages, LinkedIn, certifications, quantified achievements
- **Weak points**: Generic descriptions, missing metrics, formatting issues
- **Future-dated education**: Mark as "En curso" or "Esperando titulación"
- **Duplicate skills**: Consolidate into categorized groups (Técnicas vs Transversales)

### Step 3: Rewrite with Quantified Achievements

Transform task lists into results:
- "Asesoría legal" → "Asesoría legal para +15 clientes corporativos"
- "Elaboración de contratos" → "Elaboración de +30 contratos verificados"
- "Gestión de mediación" → "Gestión de mediación con 85% de acuerdos"
- "Seguimiento de juicios" → "Estrategias que redujeron tiempos de resolución en 20%"

### Step 4: Format Structure


NAME (bold, large)
CONTACT (centered: location | phone | email)

PERFIL PROFESIONAL (1-2 paragraphs, dual-sector highlight)

EDUCACIÓN
• Degree | Institution | Years | Status (Titulada/En curso)

EXPERIENCIA LABORAL
• Company | Role | Dates | Location
  - Achievement with metric
  - Achievement with metric

HABILIDADES CLAVE
Técnicas: • skill • skill • skill
Transversales: • skill • skill

IDIOMAS
• Language: Level (certification in progress)


### Step 5: Generate PDF Output

**Tool**: `fpdf2` (Python library, pip install fpdf2)

**Critical pitfall — Unicode**: fpdf2's default Helvetica font only supports Latin-1. Before writing any text:

python
def clean_text(text):
    replacements = {
        '–': '-', '—': '-', '–': '-',
        '‘': "'", '’': "'", '"': '"', '"': '"',
        '•': '*', '…': '...',
        '🌟': 'STAR', '🎯': '', '📚': '', '💼': '',
        '🛠️': '', '🌍': '', '📞': '', '📍': '', '✉️': '',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


**Layout**:
- Margins: 20mm left/right/top
- Font: Arial (Helvetica fallback), sizes 24/14/12/11/9
- Alignment: Title centered, section headers left-aligned
- Page break: auto with 15mm margin

### Step 6: Deliver Files

1. **Print-ready PDF**: `/home/jhon/cv_profesional.pdf` — clean, no emojis, ATS-compatible
2. **Markdown with icons**: `/home/jhon/cv_icons.md` — for preview, sharing, or copying to Word/Google Docs

## References

### references/quantification-guide.md

Guidelines for converting task descriptions into quantified achievements across different professions. Includes formulas like "Elaborar X contratos" → "Elaboración de +X contratos" and "Atender clientes" → "Atención a +X clientes con Y% de satisfacción".

### references/print-settings.md

Recommended print settings: A4 paper, 2.5cm margins, Calibri 11/Arial 11 body, bold headers, "Escala de imagen" in Word/Google Docs to preserve formatting.
