"""Generate the PWA app icons for the client portal — no third-party deps.

Full-bleed terracotta background (the portal accent) with a centered white
circle (the EYO "dot" mark). Full-bleed background keeps it maskable-safe: when
Android crops to a circle/squircle, the corners are still on-brand, never blank.

Run: python scripts/gen_pwa_icons.py  ->  static/icons/icon-{192,512}.png
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (184, 92, 56)      # #B85C38 terracotta (portal --orange)
FG = (255, 255, 255)    # white dot


def _png(width: int, height: int, rows: list[bytearray]) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    raw = bytearray()
    for row in rows:
        raw.append(0)        # filter type 0 (none)
        raw += row
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (sig + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _icon(size: int) -> bytes:
    cx = cy = (size - 1) / 2.0
    r = size * 0.30          # dot radius, well inside the 80% maskable safe zone
    r2 = r * r
    rows: list[bytearray] = []
    for y in range(size):
        row = bytearray()
        dy2 = (y - cy) ** 2
        for x in range(size):
            inside = (x - cx) ** 2 + dy2 <= r2
            row += bytes(FG if inside else BG)
        rows.append(row)
    return _png(size, size, rows)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "static" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        (out / f"icon-{size}.png").write_bytes(_icon(size))
        print(f"wrote {out / f'icon-{size}.png'}")


if __name__ == "__main__":
    main()
