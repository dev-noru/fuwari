from __future__ import annotations

import subprocess
import threading
import time
import difflib
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from PIL import Image

SCAN_INTERVAL = 0.5
SIMILARITY_THRESHOLD = 0.9


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
                char_boxes.append(CharBox(
                    char=c.get('char', ''),
                    box=(x1, y1, x2 - x1, y2 - y1),
                    confidence=conf,
                ))
                xs1.append(x1); ys1.append(y1)
                xs2.append(x2); ys2.append(y2)
                confs.append(conf)
            bx1, by1, bx2, by2 = min(xs1), min(ys1), max(xs2), max(ys2)
            regions.append(TextRegion(
                text=block.get('text', ''),
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
    def __init__(self, callback):
        self._callback = callback
        self._running = False
        self._thread = None
        self._region = None
        self._pipeline = None
        self._last_fired = ""
        self._last_regions = []

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
        cmd = ['grim', '-t', 'png']
        if self._region:
            cmd += ['-g', self._region]
        cmd += ['-']
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            return None
        img = Image.open(io.BytesIO(result.stdout)).convert('RGB')
        return np.array(img)

    @staticmethod
    def _to_sentence(regions):
        ordered = sorted(regions, key=lambda r: (r.box[1], r.box[0]))
        return ''.join(r.text for r in ordered)

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
                self._last_regions = regions
                text = self._to_sentence(regions)
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
                    self._callback(text)
            except Exception as e:
                print(f"OCR error: {e}")
            time.sleep(SCAN_INTERVAL)
