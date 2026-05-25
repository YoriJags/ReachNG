"""
ROI screenshot generator (P2 quick win).

Owner taps "Generate share card" in the portal → we render a 1200×630 PNG
("Altitude saved 47h · ₦2.4M tracked this month") that they post to IG/X.

Every Premium client who posts = ~1k free impressions in their network.
No new deps — Pillow already in stack.

Composition:
  - 1200×630 (Twitter/LinkedIn OG ratio)
  - Cream → sienna gradient background matching brand
  - Big serif headline with the ₦ figure
  - Sub-line with the time-saved figure
  - Small EYO mark + "powered by reachng.ng" footer
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import structlog

log = structlog.get_logger()


W, H = 1200, 630
CREAM = (252, 246, 234)
SIENNA = (255, 124, 71)
INK = (28, 22, 18)
INK_SOFT = (88, 78, 68)
MARK_GOLD = (255, 168, 99)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Best-effort font loader — falls back to default if system fonts absent."""
    candidates = (
        ("georgia.ttf", "Georgia.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf")
        if bold else
        ("georgia.ttf", "Georgia.ttf", "DejaVuSerif.ttf", "DejaVuSans.ttf")
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _gradient_bg() -> Image.Image:
    """Vertical cream→cream tint with a sienna glow in the bottom-right."""
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)
    # Soft sienna radial corner — cheap approximation: stack alpha rectangles
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    o_draw = ImageDraw.Draw(overlay)
    for i in range(40):
        radius = 400 + i * 12
        alpha = max(0, 20 - i // 2)
        bbox = (W - radius, H - radius, W + radius // 2, H + radius // 2)
        o_draw.ellipse(bbox, fill=(*SIENNA, alpha))
    img.paste(overlay, (0, 0), overlay)
    return img


def _fit(text: str, max_w: int, start: int, draw: ImageDraw.ImageDraw, bold: bool = False) -> ImageFont.ImageFont:
    """Pick the largest font size that fits `text` in `max_w` px, starting at `start`."""
    size = start
    while size > 24:
        f = _font(size, bold=bold)
        w = draw.textlength(text, font=f)
        if w <= max_w:
            return f
        size -= 4
    return _font(24, bold=bold)


def render_roi_card(
    *,
    business_name: str,
    naira_tracked: int = 0,
    hours_saved: float = 0.0,
    bookings: int = 0,
    period_label: str = "this month",
    agent_name: str = "EYO",
) -> bytes:
    """Render the share-card PNG and return raw bytes."""
    img = _gradient_bg()
    draw = ImageDraw.Draw(img)

    # ── Top eyebrow ─────────────────────────────────────────────────────────
    eb = _font(20, bold=True)
    draw.text((60, 56), f"{agent_name.upper()} · {period_label.upper()}", fill=SIENNA, font=eb)

    # ── Business name ──────────────────────────────────────────────────────
    name = (business_name or "Your business")[:36]
    name_font = _fit(name, W - 120, 64, draw, bold=True)
    draw.text((60, 100), name, fill=INK, font=name_font)

    # ── Big number block ────────────────────────────────────────────────────
    naira_txt = f"₦{naira_tracked:,.0f}" if naira_tracked else "Captured"
    naira_font = _fit(naira_txt, W - 120, 130, draw, bold=True)
    draw.text((60, 210), naira_txt, fill=INK, font=naira_font)

    sub_font = _font(28)
    draw.text((60, 360), "tracked through EYO", fill=INK_SOFT, font=sub_font)

    # ── Sub-stats row ───────────────────────────────────────────────────────
    stat_font = _font(28, bold=True)
    label_font = _font(18)
    stats = []
    if hours_saved:
        stats.append((f"{hours_saved:.0f}h", "saved typing"))
    if bookings:
        stats.append((f"{bookings}", "bookings captured"))
    x = 60
    for big, small in stats:
        draw.text((x, 440), big, fill=SIENNA, font=stat_font)
        draw.text((x, 478), small, fill=INK_SOFT, font=label_font)
        x += 240

    # ── Footer mark ─────────────────────────────────────────────────────────
    mark_font = _font(20, bold=True)
    sub_mark = _font(16)
    draw.text((60, H - 70), "EYO", fill=MARK_GOLD, font=mark_font)
    draw.text((110, H - 67), "· an AI WhatsApp operator", fill=INK_SOFT, font=sub_mark)
    draw.text((W - 280, H - 70), "powered by reachng.ng", fill=INK_SOFT, font=sub_mark)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
