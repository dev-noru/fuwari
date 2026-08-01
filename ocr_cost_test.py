#!/usr/bin/env python3
"""How much does full-screen OCR actually cost, and what would a gate save?

Two questions, both answered against real screenshots rather than guesses:

  1. How does OCR time scale with capture area? Detection scales with pixels,
     recognition scales with how much text is found, so a mostly-empty screen
     is not necessarily worse than a dense textbox 15x smaller.

  2. How long does comparing two frames take, compared to OCR? That is the
     gate: if comparing is cheap and the screen is usually static, most scans
     can skip OCR entirely.

    ./ocr_cost_test.py shot.png
    ./ocr_cost_test.py shot.png --box 500,1180,1400,180   # your textbox

The box is the region Fuwari would capture today, as x,y,w,h in the image's
own pixels. Without it, the bottom quarter of the image is assumed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr import MeikiPipeline  # noqa: E402

# Downscale before comparing. Enough to notice a line of text changing,
# small enough that the comparison costs nothing.
GATE_WIDTH = 160


def timed(fn, repeat):
    """Median of `repeat` runs, discarding the first as warm-up."""
    times = []
    for i in range(repeat + 1):
        t0 = time.perf_counter()
        out = fn()
        if i:  # skip warm-up
            times.append(time.perf_counter() - t0)
    times.sort()
    return times[len(times) // 2], out


def gate_signature(arr):
    """A small greyscale thumbnail, the thing two frames get compared on."""
    h, w = arr.shape[:2]
    step = max(1, w // GATE_WIDTH)
    small = arr[::step, ::step]
    return small.mean(axis=2).astype(np.float32)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--box", help="x,y,w,h of the region Fuwari captures today")
    ap.add_argument("--repeat", type=int, default=3, help="runs per measurement")
    args = ap.parse_args()

    full = np.asarray(Image.open(args.image).convert("RGB"))
    fh, fw = full.shape[:2]
    print(f"image: {args.image}  {fw}x{fh}")

    if args.box:
        x, y, w, h = (int(v) for v in args.box.split(","))
    else:
        x, y, w, h = 0, int(fh * 0.75), fw, fh - int(fh * 0.75)
    box = full[y:y + h, x:x + w]
    print(f"textbox region: {w}x{h}  ({w * h / (fw * fh) * 100:.1f}% of the screen)\n")

    pipeline = MeikiPipeline()

    print("OCR cost")
    print(f"  {'what':<16}{'pixels':>12}{'time':>10}{'chars':>8}{'blocks':>8}")
    results = {}
    for name, arr in (("textbox", box), ("full screen", full)):
        t, regions = timed(lambda a=arr: pipeline.process(a), args.repeat)
        chars = sum(len(r.chars or []) for r in regions)
        results[name] = (t, arr.shape[0] * arr.shape[1], chars, len(regions))
        print(f"  {name:<16}{arr.shape[0] * arr.shape[1]:>12,}{t * 1000:>9.0f}ms"
              f"{chars:>8}{len(regions):>8}")

    tb, fs = results["textbox"], results["full screen"]
    area_ratio = fs[1] / tb[1]
    time_ratio = fs[0] / tb[0]
    print(f"\n  full screen is {area_ratio:.1f}x the pixels and {time_ratio:.1f}x the time")
    if time_ratio < area_ratio * 0.5:
        print("  -> scales better than area; recognition dominates, not detection")

    print("\nFrame gate")
    sig = gate_signature(full)
    t_sig, _ = timed(lambda: gate_signature(full), 20)
    t_cmp, _ = timed(lambda: float(np.abs(gate_signature(full) - sig).mean()), 20)
    print(f"  thumbnail + compare: {t_cmp * 1000:.2f}ms  ({sig.shape[1]}x{sig.shape[0]})")
    print(f"  full-screen OCR    : {fs[0] * 1000:.0f}ms")
    print(f"  gate is {fs[0] / t_cmp:.0f}x cheaper than the OCR it skips")

    # What that means over a minute of reading, at Fuwari's 0.5s interval.
    scans = 120
    for changed_pct in (5, 20, 50):
        changed = scans * changed_pct // 100
        now = scans * fs[0]
        gated = scans * t_cmp + changed * fs[0]
        print(f"\n  60s at {changed_pct}% of scans showing new text:")
        print(f"    today {now:>6.1f}s of CPU   gated {gated:>6.1f}s"
              f"   ({(1 - gated / now) * 100:.0f}% less)")

    print("\nA gate only helps if the screen is genuinely still while reading.")
    print("Run this against a real capture of the game you care about.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
