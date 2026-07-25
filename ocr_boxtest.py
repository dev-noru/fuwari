#!/usr/bin/env python3
"""
Offline check on MeikiOCR's per-character boxes.

Runs the real MeikiPipeline from ocr.py against a still image, draws what it
returns, and reports the geometry stats that matter for hit-testing. No Wayland,
no layer surface, no FFI -- just: are the boxes tight enough to hover?

    ./ocr_boxtest.py shot.png
    ./ocr_boxtest.py shot.png -o out.png --no-labels

Read the two outputs together: the report tells you if the numbers are sane, the
image tells you if they're actually on the glyphs.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr import MeikiPipeline, TextRegion  # noqa: E402


BLOCK_COLOR = (80, 170, 255)
LABEL_COLOR = (255, 255, 0)
OUTLIER_COLOR = (255, 0, 255)

FONT_CANDIDATES = [
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/OTF/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/TTF/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/adobe-source-han-sans-jp/SourceHanSansJP-Regular.otf",
]

# A box more than this fraction away from the region's median side length is
# called out as an outlier -- usually two glyphs merged, or a stray detection.
OUTLIER_TOLERANCE = 0.40

# Overlap between neighbours above this fraction of a cell makes the character
# under the cursor ambiguous.
OVERLAP_WARN = 0.25


def load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def conf_color(conf: float) -> tuple[int, int, int]:
    """Green at 1.0, red at 0.5 and below."""
    t = max(0.0, min(1.0, (conf - 0.5) / 0.5))
    return (int(255 * (1 - t)), int(200 * t + 40), 40)


def axis_positions(region: TextRegion) -> list[float]:
    """Leading edge of each cell along the reading axis.

    Leading edge rather than centre: a box that comes back too wide would drag
    its own centre sideways and show up as an advance irregularity, hiding the
    fact that the cell origins are actually on a clean grid. Width problems are
    already reported separately as size outliers.
    """
    if region.vertical:
        return [c.box[1] for c in region.chars]
    return [c.box[0] for c in region.chars]


def analyse(region: TextRegion, idx: int) -> list[str]:
    lines = []
    chars = region.chars or []
    direction = "vertical" if region.vertical else "horizontal"
    lines.append(
        f"region {idx}: {direction}  {len(chars)} chars  "
        f"conf {region.confidence:.3f}  box {region.box}"
    )
    lines.append(f"  text: {region.text}")

    if not chars:
        lines.append("  !! no per-character boxes -- everything downstream needs them")
        return lines

    if len(region.text) != len(chars):
        lines.append(
            f"  !! text is {len(region.text)} chars but {len(chars)} boxes came back; "
            f"index -> character mapping will be wrong"
        )

    widths = [c.box[2] for c in chars]
    heights = [c.box[3] for c in chars]
    med_w = statistics.median(widths)
    med_h = statistics.median(heights)
    lines.append(
        f"  cell size: median {med_w:.0f}x{med_h:.0f}  "
        f"w range {min(widths)}-{max(widths)}  h range {min(heights)}-{max(heights)}"
    )

    degenerate = [i for i, c in enumerate(chars) if c.box[2] <= 0 or c.box[3] <= 0]
    if degenerate:
        lines.append(f"  !! zero-area boxes at {degenerate}")

    outliers = []
    for i, c in enumerate(chars):
        dw = abs(c.box[2] - med_w) / med_w if med_w else 0
        dh = abs(c.box[3] - med_h) / med_h if med_h else 0
        if dw > OUTLIER_TOLERANCE or dh > OUTLIER_TOLERANCE:
            outliers.append((i, c.char, c.box))
    if outliers:
        lines.append(f"  {len(outliers)} size outlier(s) (drawn magenta):")
        for i, ch, box in outliers[:8]:
            lines.append(f"    [{i}] {ch!r} {box}")
        if len(outliers) > 8:
            lines.append(f"    ... and {len(outliers) - 8} more")

    # Advance regularity along the reading axis. Big spread means the boxes
    # aren't tracking a consistent grid.
    pos = axis_positions(region)
    order = sorted(range(len(pos)), key=lambda i: pos[i])
    if order != list(range(len(pos))):
        lines.append("  !! boxes are not in reading order along their own axis")
    steps = [b - a for a, b in zip(sorted(pos), sorted(pos)[1:])]
    if steps:
        med_step = statistics.median(steps)
        spread = (max(steps) - min(steps)) / med_step if med_step else 0
        lines.append(
            f"  advance: median {med_step:.1f}px  min {min(steps):.1f}  "
            f"max {max(steps):.1f}  spread {spread * 100:.0f}%"
        )

    # Neighbour overlap along the reading axis -- ambiguous hit-testing.
    ordered = sorted(chars, key=lambda c: c.box[1] if region.vertical else c.box[0])
    worst = 0.0
    worst_pair = None
    for a, b in zip(ordered, ordered[1:]):
        if region.vertical:
            a_end, b_start, cell = a.box[1] + a.box[3], b.box[1], med_h
        else:
            a_end, b_start, cell = a.box[0] + a.box[2], b.box[0], med_w
        ov = (a_end - b_start) / cell if cell else 0
        if ov > worst:
            worst, worst_pair = ov, (a.char, b.char)
    if worst > OVERLAP_WARN:
        lines.append(
            f"  !! neighbours overlap by up to {worst * 100:.0f}% of a cell "
            f"({worst_pair[0]!r}/{worst_pair[1]!r}) -- hit-testing will be ambiguous"
        )
    else:
        lines.append(f"  max neighbour overlap: {max(worst, 0) * 100:.0f}% of a cell")

    weak = [(i, c.char, c.confidence) for i, c in enumerate(chars) if c.confidence < 0.6]
    if weak:
        lines.append(f"  {len(weak)} low-confidence char(s):")
        for i, ch, cf in weak[:8]:
            lines.append(f"    [{i}] {ch!r} {cf:.3f}")

    return lines


def draw(image: Image.Image, regions: list[TextRegion], labels: bool) -> Image.Image:
    out = image.convert("RGB")
    d = ImageDraw.Draw(out)

    for region in regions:
        chars = region.chars or []
        med_w = statistics.median([c.box[2] for c in chars]) if chars else 0
        med_h = statistics.median([c.box[3] for c in chars]) if chars else 0
        font = load_font(max(11, int(med_h * 0.32))) if labels and med_h else None

        bx, by, bw, bh = region.box
        d.rectangle([bx, by, bx + bw, by + bh], outline=BLOCK_COLOR, width=2)

        for i, c in enumerate(chars):
            x, y, w, h = c.box
            dw = abs(w - med_w) / med_w if med_w else 0
            dh = abs(h - med_h) / med_h if med_h else 0
            is_outlier = dw > OUTLIER_TOLERANCE or dh > OUTLIER_TOLERANCE
            color = OUTLIER_COLOR if is_outlier else conf_color(c.confidence)
            d.rectangle([x, y, x + w, y + h], outline=color, width=1)

            if font is not None:
                # Recognised glyph above the cell -- compare it against what's
                # actually inside the box.
                d.text((x, y - med_h * 0.36), c.char, fill=LABEL_COLOR, font=font)
                d.text((x, y + h + 1), str(i), fill=BLOCK_COLOR, font=font)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="still image to OCR")
    ap.add_argument("-o", "--out", default=None,
                    help="annotated output path (default: <image>.boxes.png)")
    ap.add_argument("--no-labels", action="store_true",
                    help="skip glyph/index labels")
    args = ap.parse_args()

    if not os.path.exists(args.image):
        print(f"no such file: {args.image}", file=sys.stderr)
        return 1

    src = Image.open(args.image).convert("RGB")
    arr = np.asarray(src)
    print(f"image: {args.image}  {src.width}x{src.height}")

    pipeline = MeikiPipeline()
    regions = pipeline.process(arr)

    if not regions:
        print("no regions returned -- nothing to align against")
        return 2

    total = sum(len(r.chars or []) for r in regions)
    print(f"regions: {len(regions)}  characters: {total}\n")
    for i, region in enumerate(regions):
        for line in analyse(region, i):
            print(line)
        print()

    out_path = args.out or os.path.splitext(args.image)[0] + ".boxes.png"
    draw(src, regions, labels=not args.no_labels).save(out_path)
    print(f"wrote {out_path}")
    print("green = confident, red = weak, magenta = size outlier, blue = block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
