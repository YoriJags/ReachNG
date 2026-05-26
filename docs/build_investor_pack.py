"""
Build a single investor-ready PDF stitched from ECONOMICS.md, PRICING.md,
and INVESTOR.md.

Run:  python -m docs.build_investor_pack
Out:  docs/pdfs/INVESTOR_PACK.pdf

Reuses the renderer in legal.build_pdfs (markdown -> reportlab flowables)
so the cosmetic style matches the legal pack visitors already trust.
Adds a cover page + section dividers between the three sources.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, Spacer, SimpleDocTemplate, Table, TableStyle,
)

# Reuse the renderer pieces already proven in the legal pipeline.
from legal.build_pdfs import _build_styles, _md_to_flowables


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR   = Path(__file__).parent / "pdfs"

# Order = how an investor should read it: business model first, then prices,
# then the operating numbers underneath.
SOURCES = [
    ("Investor brief",        REPO_ROOT / "INVESTOR.md"),
    ("Pricing & packaging",   REPO_ROOT / "PRICING.md"),
    ("Unit economics",        REPO_ROOT / "ECONOMICS.md"),
]


# ─── Cover page ──────────────────────────────────────────────────────────────

def _cover_flowables(styles: dict) -> list:
    # %-d is Unix-only — use %d and strip the leading zero for cross-platform.
    now = datetime.now(timezone.utc)
    today = f"{now.day} {now.strftime('%B %Y')}"

    out = []
    out.append(Spacer(1, 70 * mm))

    out.append(Paragraph(
        '<font color="#ff5c00">ReachNG</font>',
        styles["h1"]._replace() if hasattr(styles["h1"], "_replace") else styles["h1"],
    ))
    out.append(Spacer(1, 4 * mm))
    out.append(Paragraph(
        "Investor Pack",
        styles["h1"],
    ))
    out.append(Spacer(1, 12 * mm))
    out.append(Paragraph(
        "The WhatsApp employee for Lagos &amp; Abuja businesses.",
        styles["body"],
    ))
    out.append(Spacer(1, 60 * mm))

    # Contents table
    contents = [
        [Paragraph("<b>Section</b>", styles["body"]),  Paragraph("<b>Source</b>", styles["body"])],
        [Paragraph("1. Investor brief",    styles["body"]),  Paragraph("INVESTOR.md",  styles["body"])],
        [Paragraph("2. Pricing &amp; packaging", styles["body"]),  Paragraph("PRICING.md",   styles["body"])],
        [Paragraph("3. Unit economics",    styles["body"]),  Paragraph("ECONOMICS.md", styles["body"])],
    ]
    tbl = Table(contents, colWidths=[110 * mm, 60 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#f5f7fa")),
        ("LINEABOVE",     (0, 0), (-1, 0), 0.4, colors.HexColor("#cccccc")),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    out.append(tbl)
    out.append(Spacer(1, 40 * mm))

    out.append(Paragraph(
        f'<font color="#888888">Compiled {today} &nbsp;·&nbsp; Yori Ajagun &nbsp;·&nbsp; yoriajagun08@gmail.com</font>',
        styles["body"],
    ))

    out.append(PageBreak())
    return out


def _section_divider(title: str, styles: dict) -> list:
    out = [Spacer(1, 60 * mm)]
    out.append(Paragraph(
        f'<font color="#ff5c00">§ {title}</font>',
        styles["h1"],
    ))
    out.append(PageBreak())
    return out


# ─── Page furniture ──────────────────────────────────────────────────────────

def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawString(20 * mm, 12 * mm, "ReachNG · Investor Pack")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canvas.line(20 * mm, 18 * mm, 190 * mm, 18 * mm)
    canvas.restoreState()


# ─── Build ───────────────────────────────────────────────────────────────────

def build() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / "INVESTOR_PACK.pdf"
    styles = _build_styles()

    flow: list = []
    flow += _cover_flowables(styles)

    for label, md_path in SOURCES:
        if not md_path.exists():
            print(f"[WARN] missing source: {md_path}", file=sys.stderr)
            continue
        flow += _section_divider(label, styles)
        md = md_path.read_text(encoding="utf-8")
        flow += _md_to_flowables(md, styles)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm,  bottomMargin=22 * mm,
        title="ReachNG · Investor Pack", author="ReachNG",
    )
    doc.title = "Investor Pack"
    doc.build(flow, onFirstPage=_on_page, onLaterPages=_on_page)
    return out_path


if __name__ == "__main__":
    p = build()
    print(f"[OK] -> {p.relative_to(REPO_ROOT)}")
