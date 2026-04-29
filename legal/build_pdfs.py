"""
Convert the 4 legal markdown documents to professional-looking PDFs.

Run: python -m legal.build_pdfs
Output: legal/pdfs/{MSA,DPA,MUTUAL_NDA,CLOSER_ADDENDUM,README}.pdf

Uses reportlab — pure Python, no system deps beyond a working pip install.
The renderer is intentionally light on markdown features (handles headings,
paragraphs, lists, tables, bold/italic, code spans) — enough for these
contract-style documents.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether,
)


HERE = Path(__file__).parent
OUT_DIR = HERE / "pdfs"
DOCS = ["README", "MSA", "DPA", "MUTUAL_NDA", "CLOSER_ADDENDUM"]


# ─── Styles ──────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, spaceBefore=4, spaceAfter=10,
            textColor=colors.HexColor("#1a1f28"),
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=18, spaceBefore=14, spaceAfter=6,
            textColor=colors.HexColor("#ff5c00"),
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=11, leading=15, spaceBefore=10, spaceAfter=4,
            textColor=colors.HexColor("#1a1f28"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=15, spaceAfter=8,
            textColor=colors.HexColor("#1a1f28"),
        ),
        "li": ParagraphStyle(
            "li", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=14, spaceAfter=4, leftIndent=18,
            bulletIndent=6,
        ),
        "review": ParagraphStyle(
            "review", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=9, leading=13, spaceAfter=8, leftIndent=8,
            backColor=colors.HexColor("#fff6e6"),
            borderPadding=4, borderColor=colors.HexColor("#ff9933"), borderWidth=0.5,
            textColor=colors.HexColor("#7a3300"),
        ),
        "hr": ParagraphStyle(
            "hr", parent=base["BodyText"], fontSize=8, spaceAfter=6,
        ),
    }


# ─── Markdown → flowables ────────────────────────────────────────────────────

_BOLD_RE   = re.compile(r"\*\*(.+?)\*\*")
_ITAL_RE   = re.compile(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)")
_CODE_RE   = re.compile(r"`([^`]+)`")
_LINK_RE   = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")
_REVIEW_RE = re.compile(r"\[LAWYER REVIEW\]")


def _inline(text: str) -> str:
    """Convert inline markdown to ReportLab's mini-HTML."""
    # Order matters: code first to protect from other regexes
    text = _CODE_RE.sub(r'<font face="Courier" color="#3a3a3a">\1</font>', text)
    text = _LINK_RE.sub(r'<u>\1</u>', text)  # links flattened — references are obvious from filename
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITAL_RE.sub(r"<i>\1</i>", text)
    text = _REVIEW_RE.sub(r'<font color="#7a3300"><b>[LAWYER REVIEW]</b></font>', text)
    # Escape ampersands that aren't already entities
    text = re.sub(r"&(?!amp;|lt;|gt;|#)", "&amp;", text)
    return text


def _md_to_flowables(md: str, styles: dict) -> list:
    flowables = []
    lines = md.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.rstrip()

        # Headings
        if stripped.startswith("# "):
            flowables.append(Paragraph(_inline(stripped[2:]), styles["h1"]))
            i += 1
            continue
        if stripped.startswith("## "):
            flowables.append(Paragraph(_inline(stripped[3:]), styles["h2"]))
            i += 1
            continue
        if stripped.startswith("### "):
            flowables.append(Paragraph(_inline(stripped[4:]), styles["h3"]))
            i += 1
            continue

        # Horizontal rule — render as a thin spacer
        if re.match(r"^-{3,}\s*$", stripped):
            flowables.append(Spacer(1, 4))
            tbl = Table([[" "]], colWidths=[170 * mm], rowHeights=[0.4])
            tbl.setStyle(TableStyle([
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, colors.HexColor("#cccccc")),
            ]))
            flowables.append(tbl)
            flowables.append(Spacer(1, 8))
            i += 1
            continue

        # Tables
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|\s*[-:|\s]+\|\s*$", lines[i + 1]):
            tbl_lines = [stripped]
            j = i + 2  # skip separator
            while j < n and lines[j].lstrip().startswith("|"):
                tbl_lines.append(lines[j].rstrip())
                j += 1
            flowables.append(_render_table(tbl_lines, styles))
            i = j
            continue

        # Numbered or bulleted list block
        if re.match(r"^(\s*[-*]\s+|\s*\d+\.\s+)", stripped):
            list_lines = []
            while i < n and (re.match(r"^(\s*[-*]\s+|\s*\d+\.\s+)", lines[i]) or
                             (lines[i].startswith("  ") and list_lines)):
                list_lines.append(lines[i])
                i += 1
            flowables.extend(_render_list(list_lines, styles))
            continue

        # Paragraph (collect lines until blank)
        if stripped:
            para_lines = [stripped]
            i += 1
            while i < n and lines[i].rstrip() and not _starts_block(lines[i]):
                para_lines.append(lines[i].rstrip())
                i += 1
            text = " ".join(para_lines)
            style = styles["review"] if "[LAWYER REVIEW]" in text else styles["body"]
            flowables.append(Paragraph(_inline(text), style))
            continue

        # Blank line — small space
        i += 1

    return flowables


def _starts_block(line: str) -> bool:
    s = line.lstrip()
    return (
        s.startswith("#")
        or s.startswith("|")
        or re.match(r"^([-*]\s+|\d+\.\s+)", s) is not None
        or re.match(r"^-{3,}\s*$", line.rstrip()) is not None
    )


def _render_list(lines: list[str], styles: dict) -> list:
    out = []
    for raw in lines:
        m = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)$", raw)
        if not m:
            # Continuation line — append to last paragraph
            if out:
                last = out[-1]
                if isinstance(last, Paragraph):
                    last_text = last.text + " " + raw.strip()
                    out[-1] = Paragraph(_inline(last_text), styles["li"])
            continue
        text = m.group(1)
        out.append(Paragraph("• " + _inline(text), styles["li"]))
    return out


def _render_table(lines: list[str], styles: dict) -> Table:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cells = [Paragraph(_inline(c), styles["body"]) for c in cells]
        rows.append(cells)
    if not rows:
        return Spacer(1, 0)
    n_cols = len(rows[0])
    col_w = (170 * mm) / n_cols
    tbl = Table(rows, colWidths=[col_w] * n_cols, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#f5f7fa")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOX",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("INNERGRID",    (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    return tbl


# ─── Page furniture ──────────────────────────────────────────────────────────

def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawString(20 * mm, 12 * mm, f"ReachNG · {doc.title}")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canvas.line(20 * mm, 18 * mm, 190 * mm, 18 * mm)
    canvas.restoreState()


# ─── Build ───────────────────────────────────────────────────────────────────

def build_one(slug: str) -> Path:
    md_path = HERE / f"{slug}.md"
    if not md_path.exists():
        raise FileNotFoundError(md_path)
    md = md_path.read_text(encoding="utf-8")
    OUT_DIR.mkdir(exist_ok=True)
    pdf_path = OUT_DIR / f"{slug}.pdf"

    title = _extract_title(md) or slug
    styles = _build_styles()
    flowables = _md_to_flowables(md, styles)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=22 * mm,
        title=title, author="ReachNG",
    )
    doc.title = title
    doc.build(flowables, onFirstPage=_on_page, onLaterPages=_on_page)
    return pdf_path


def _extract_title(md: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def main():
    OUT_DIR.mkdir(exist_ok=True)
    results = []
    for slug in DOCS:
        try:
            path = build_one(slug)
            print(f"[OK] {slug:18s} -> {path.relative_to(HERE.parent)}")
            results.append((slug, path, None))
        except Exception as e:
            print(f"[FAIL] {slug:18s} {e}", file=sys.stderr)
            results.append((slug, None, e))
    failures = [r for r in results if r[2]]
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
