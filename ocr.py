from __future__ import annotations

import threading
import time
import difflib
from abc import ABC, abstractmethod
from dataclasses import dataclass

SCAN_INTERVAL = 0.5
SIMILARITY_THRESHOLD = 0.9

# A box narrower or shorter than this can't be hovered, and the character it
# claims to hold shifts every offset after it. Drop them.
MIN_CHAR_SIDE = 4

# Detections below this are usually icons, borders or window chrome read as
# text. Real glyphs sit far above it.
MIN_CHAR_CONF = 0.25


@dataclass
class CharBox:
    char: str
    box: tuple[int, int, int, int]      # (x, y, w, h), capture-image coords
    confidence: float


@dataclass
class TextRegion:
    text: str
    box: tuple[int, int, int, int]      # (x, y, w, h), capture-image coords
    vertical: bool
    confidence: float                   # block-level, mean of char confidences
    chars: list[CharBox] | None = None  # per-char detail when the engine has it


class OCRPipeline(ABC):
    @abstractmethod
    def process(self, image) -> list[TextRegion]:
        """Take an RGB numpy image, return a list of TextRegion."""
        ...


class MeikiPipeline(OCRPipeline):
    def __init__(self):
        from meikiocr import MeikiOCR
        self._model = MeikiOCR()

    def process(self, image) -> list[TextRegion]:
        raw = self._model.run_ocr(image)
        regions = []
        for block in raw:
            chars = block.get('chars') or []
            if not chars:
                continue
            char_boxes = []
            xs1, ys1, xs2, ys2, confs = [], [], [], [], []
            for c in chars:
                x1, y1, x2, y2 = c['bbox']
                conf = c.get('conf', 0.0)
                if x2 - x1 < MIN_CHAR_SIDE or y2 - y1 < MIN_CHAR_SIDE:
                    continue
                if conf < MIN_CHAR_CONF:
                    continue
                char_boxes.append(CharBox(
                    char=c.get('char', ''),
                    box=(x1, y1, x2 - x1, y2 - y1),
                    confidence=conf,
                ))
                xs1.append(x1); ys1.append(y1)
                xs2.append(x2); ys2.append(y2)
                confs.append(conf)
            if not char_boxes:
                continue
            # Box comes from the surviving characters, not the raw block, so a
            # dropped detection can't leave the region stretched around nothing.
            bx1, by1, bx2, by2 = min(xs1), min(ys1), max(xs2), max(ys2)
            regions.append(TextRegion(
                text=''.join(c.char for c in char_boxes),
                box=(bx1, by1, bx2 - bx1, by2 - by1),
                vertical=block.get('is_vertical', False),
                confidence=sum(confs) / len(confs),
                chars=char_boxes,
            ))
        return regions


_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline() -> OCRPipeline:
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = MeikiPipeline()
    return _pipeline


def is_pipeline_loaded() -> bool:
    return _pipeline is not None


def ensure_pipeline_loaded() -> None:
    _get_pipeline()


class OCRThread:
    def __init__(self, callback, layershell, on_geometry=None):
        self._callback = callback
        self._on_geometry = on_geometry
        self._layershell = layershell
        self._running = False
        self._thread = None
        self._region = None
        self._pipeline = None
        self._last_fired = ""
        self._last_regions = []
        self._last_chars = []
        self._last_frame = None

    def start(self):
        self._pipeline = _get_pipeline()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._region = None

    def set_region(self, region_str):
        self._region = region_str

    def _capture(self):
        if not self._region:
            return None
        # region_str is slurp's "x,y WxH" (layout coords)
        xy, wh = self._region.split()
        x, y = map(int, xy.split(','))
        w, h = map(int, wh.split('x'))
        # Kept so character boxes, which come back in capture-image physical
        # pixels, can be put back on the screen later: the origin shifts them
        # and physical_width / w gives the scale to divide by.
        self._capture_origin = (x, y)
        self._capture_logical = (w, h)
        return self._layershell.capture(x, y, w, h)

    @staticmethod
    def _order_regions(regions):
        """Reading order between regions.

        Vertical Japanese runs top-to-bottom in columns that advance right to
        left, so the primary key flips sign and the axes swap.
        """
        if not regions:
            return []
        vertical = sum(r.vertical for r in regions) * 2 > len(regions)
        if vertical:
            return sorted(regions, key=lambda r: (-r.box[0], r.box[1]))
        return sorted(regions, key=lambda r: (r.box[1], r.box[0]))

    @staticmethod
    def _flatten(ordered):
        """Sentence plus the box behind each of its characters.

        Built from the character boxes rather than from block text, so
        sentence[i] and chars[i] refer to the same glyph by construction. Any
        token offset computed on the sentence indexes straight into chars.
        """
        chars = []
        for region in ordered:
            chars.extend(region.chars or [])
        return ''.join(c.char for c in chars), chars

    def _to_sentence(self, regions):
        return self._flatten(self._order_regions(regions))[0]

    def _loop(self):
        last_text = ""
        stable_count = 0
        while self._running:
            try:
                if not self._region:
                    time.sleep(SCAN_INTERVAL)
                    continue
                img = self._capture()
                if img is None:
                    time.sleep(SCAN_INTERVAL)
                    continue
                regions = self._pipeline.process(img)
                ordered = self._order_regions(regions)
                text, chars = self._flatten(ordered)
                self._last_regions = ordered
                self._last_chars = chars
                if not text:
                    stable_count = 0
                    last_text = ""
                    time.sleep(SCAN_INTERVAL)
                    continue
                ratio = difflib.SequenceMatcher(None, last_text, text).ratio()
                if ratio >= SIMILARITY_THRESHOLD:
                    stable_count += 1
                else:
                    stable_count = 1
                last_text = text
                if stable_count == 2 and text != self._last_fired:
                    self._last_fired = text
                    # Frame is retained only once the text has settled, so the
                    # pixels behind the boxes match the boxes themselves.
                    self._last_frame = img
                    self._callback(text)
                    if self._on_geometry:
                        self._on_geometry(chars, self._capture_origin,
                                          self._capture_logical, img)
            except Exception as e:
                print(f"OCR error: {e}")
            time.sleep(SCAN_INTERVAL)
