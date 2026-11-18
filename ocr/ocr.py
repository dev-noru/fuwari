from __future__ import annotations

import threading
import time
import difflib
from abc import ABC, abstractmethod
from dataclasses import dataclass

SCAN_INTERVAL = 0.5
SIMILARITY_THRESHOLD = 0.9
# Line grouping. meikiocr returns one entry per text line, so a word that
# wraps would otherwise be tokenized as two halves. Measured in units of the
# line's own character size, so they hold at any resolution.
LINE_GAP_MAX = 1.0        # widest gap between consecutive lines, in chars
LINE_ALIGN_MAX = 1.5      # how far their start edges may disagree, in chars
LINE_SIZE_RATIO = 1.33    # how different their character sizes may be

# Frame gate. Recognising text costs ~90ms; comparing two frames costs ~0.4ms,
# so checking whether anything moved before running OCR is around 200x cheaper
# than running it and discovering nothing changed. While you are reading a
# line the screen is still, which is most scans.
GATE_WIDTH = 160          # thumbnail width the comparison runs on
GATE_EPSILON = 0.35       # mean 0-255 difference below this counts as unchanged
# How much the screen outside a highlighted word may change before the
# highlight counts as stale. Well above GATE_EPSILON: while reading, small
# things still move (a blinking sprite, a game cursor), and only a real
# change of screen should end the hover.
STALE_EPSILON = 2.0
# How long the popup mask must stay put before frames are captured again.
# The popup is drawn before its new mask reaches this thread, and the portal's
# frames can trail the screen slightly, so a frame taken while it moves can
# hold a popup the mask does not cover. Recognised, that frame becomes the
# reference every later frame is compared with, and the popup in it makes the
# screen look changed from then on.
MASK_SETTLE = 0.35
# A box narrower or shorter than this can't be hovered, and the character it
# claims to hold shifts every offset after it. Drop them.
MIN_CHAR_SIDE = 4

# Characters recognised with less confidence than this are dropped. The
# default for when no setting is passed; the OCR tab chooses between 0.1
# (what meikipop uses), this, and a stricter 0.4. Small or thin text reads
# with lower confidence even when it is read correctly, so on web pages a
# stricter value drops real characters and glues their neighbours together.
MIN_CHAR_CONF = 0.25

# Stability filter. An animated background makes the detector find "text" in
# moving shapes, and those boxes appear, vanish and jump around from scan to
# scan. Real text stays put. A box is kept only if a box in the same place
# (overlap of at least STABLE_IOU) was found in STABLE_HITS of the last
# STABLE_WINDOW recognitions. Only recognitions count, not gated scans.
STABLE_HITS = 2
STABLE_WINDOW = 3
STABLE_IOU = 0.5


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


class RegionTracker:
    """Drops text regions that do not hold still across recognitions.

    Each track remembers, for the last STABLE_WINDOW recognitions, whether a
    region in its place was found. Regions are matched to tracks by IoU on
    their boxes alone, never by their pixels or text, so a moving background
    behind real text does not make that text look unstable.
    """

    def __init__(self, hits=STABLE_HITS, window=STABLE_WINDOW, iou=STABLE_IOU):
        self._hits = hits
        self._window = window
        self._iou = iou
        self._tracks = []   # each: [box, deque of bools]

    def reset(self):
        self._tracks = []

    @staticmethod
    def _overlap(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        iw = min(ax + aw, bx + bw) - max(ax, bx)
        ih = min(ay + ah, by + bh) - max(ay, by)
        if iw <= 0 or ih <= 0:
            return 0.0
        inter = iw * ih
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0

    def update(self, regions):
        """Record one recognition's regions; return the ones that are stable."""
        from collections import deque

        # Best overlaps first, so each region claims the track it fits best
        # and two regions can't share one track.
        pairs = []
        for ri, region in enumerate(regions):
            for ti, (box, _) in enumerate(self._tracks):
                score = self._overlap(region.box, box)
                if score >= self._iou:
                    pairs.append((score, ri, ti))
        pairs.sort(reverse=True)

        region_track = {}
        used_tracks = set()
        for _, ri, ti in pairs:
            if ri in region_track or ti in used_tracks:
                continue
            region_track[ri] = ti
            used_tracks.add(ti)

        # Matched tracks follow their region, so text that grows in place
        # (typewriter effect) keeps the same track.
        for ri, ti in region_track.items():
            self._tracks[ti][0] = regions[ri].box
            self._tracks[ti][1].append(True)
        for ti, track in enumerate(self._tracks):
            if ti not in used_tracks:
                track[1].append(False)

        # Unmatched regions start new tracks.
        for ri, region in enumerate(regions):
            if ri not in region_track:
                history = deque([True], maxlen=self._window)
                region_track[ri] = len(self._tracks)
                self._tracks.append([region.box, history])

        kept = [region for ri, region in enumerate(regions)
                if sum(self._tracks[region_track[ri]][1]) >= self._hits]

        # A track with no hits left in its window is gone from the screen.
        # Dropping it keeps the list bounded however long the app runs.
        self._tracks = [t for t in self._tracks if any(t[1])]
        return kept

    def known(self, regions):
        """The regions that sit on a track that is currently stable.

        Read-only: for checking a frame against what is already on screen
        without counting it as a recognition.
        """
        stable = [box for box, history in self._tracks
                  if sum(history) >= self._hits]
        return [r for r in regions
                if any(self._overlap(r.box, box) >= self._iou
                       for box in stable)]


class OCRPipeline(ABC):
    @abstractmethod
    def process(self, image, min_conf=MIN_CHAR_CONF) -> list[TextRegion]:
        """Take an RGB numpy image, return a list of TextRegion."""
        ...


class MeikiPipeline(OCRPipeline):
    def __init__(self):
        from meikiocr import MeikiOCR
        self._model = MeikiOCR()

    def process(self, image, min_conf=MIN_CHAR_CONF) -> list[TextRegion]:
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
                if conf < min_conf:
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


def _disable_onnx_arena() -> None:
    """Stop ONNX Runtime's CPU memory arena growing without bound.

    The arena is on by default and never returns memory to the OS, so a scan
    every SCAN_INTERVAL grows resident memory for as long as the app runs --
    gigabytes over a few hours. It is a property of the session, which the OCR
    engine creates internally, so the option is injected by wrapping the
    constructor rather than by patching the engine.

    Costs a little latency per inference, since allocation is no longer served
    from a pre-grown pool.
    """
    try:
        import onnxruntime
    except ImportError:
        return
    if getattr(onnxruntime.InferenceSession, '_fuwari_no_arena', False):
        return

    original = onnxruntime.InferenceSession.__init__

    def patched(self, *args, **kwargs):
        opts = kwargs.get('sess_options')
        if opts is None and len(args) > 1 and isinstance(args[1], onnxruntime.SessionOptions):
            opts = args[1]
        if opts is None:
            opts = onnxruntime.SessionOptions()
            kwargs['sess_options'] = opts
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        return original(self, *args, **kwargs)

    onnxruntime.InferenceSession.__init__ = patched
    onnxruntime.InferenceSession._fuwari_no_arena = True


def _get_pipeline() -> OCRPipeline:
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _disable_onnx_arena()
                _pipeline = MeikiPipeline()
    return _pipeline


def is_pipeline_loaded() -> bool:
    return _pipeline is not None


def ensure_pipeline_loaded() -> None:
    _get_pipeline()


class OCRThread:
    def __init__(self, callback, layershell, on_geometry=None, portal=None,
                 on_stale=None, scan_interval=SCAN_INTERVAL,
                 stale_epsilon=STALE_EPSILON, join_lines=True,
                 min_char_conf=MIN_CHAR_CONF):
        self._callback = callback
        self._on_geometry = on_geometry
        self._layershell = layershell
        self._running = False
        # Set while Fuwari's own popup is on screen. The popup is drawn over
        # the captured area, so its pixels change the frame, which trips the
        # change gate and runs full recognition -- on the popup's own text.
        # Hovering words then costs a recognition pass each time.
        self._paused = False
        # Set on desktops where grim cannot capture (KWin, Mutter).
        self._portal = portal
        # Set while Fuwari's hover highlight is on screen. The highlight is
        # drawn over the glyphs being read, so recognising a frame with it in
        # would read tinted text. It also stands in for a game's own cursor:
        # a cursor resting on a word means that word is hovered.
        self._highlighting = False
        # Called when the screen changes under a highlight, so the bridge can
        # drop the hover and the boxes that belong to the old screen.
        self._on_stale = on_stale
        # From the OCR settings tab; the module constants are the defaults.
        self._scan_interval = scan_interval
        self._stale_epsilon = stale_epsilon
        self._join_lines = join_lines
        self._min_char_conf = min_char_conf
        # The highlighted word's box in capture pixels, left out when checking
        # whether the screen has moved on, since the highlight itself changes
        # those pixels.
        self._highlight_rect = None
        # Where the popup mask was blanked in the last capture, left out for
        # the same reason.
        self._mask_px = None
        # Where it was blanked in the frame _last_sig came from. The popup
        # moves between words, so the spot it used to cover shows the game
        # again, which is not the screen changing either.
        self._last_sig_mask = None
        # Consecutive scans that looked like the screen had moved on. One is
        # not enough: the popup can appear a moment before its mask reaches
        # this thread, and that single frame looks like a new screen.
        self._stale_hits = 0
        # When the popup mask last changed, for MASK_SETTLE.
        self._mask_changed_at = 0.0
        self._thread = None
        self._region = None
        self._mask = None
        self._pipeline = None
        self._last_fired = ""
        self._last_regions = []
        self._last_blocks = []
        self._last_sig = None
        self._scans = 0
        self._recognitions = 0
        self._tracker = RegionTracker()
        # The last recognition's regions before filtering, and whether the
        # filter held any back. A gated scan (identical pixels) re-detects
        # exactly these, so it can give them their second sighting without
        # running OCR again.
        self._last_raw = []
        self._held_back = False

    def start(self):
        self._pipeline = _get_pipeline()
        from ocr.portal import portal_needed, PortalCapture, PortalCancelled
        if self._portal is None and portal_needed():
            portal = PortalCapture()
            try:
                portal.start()
            except PortalCancelled:
                print("screen share cancelled; OCR not started")
                portal.stop()
                return
            except Exception as e:
                print("portal capture failed:", e)
                portal.stop()
                return
            self._portal = portal
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._region = None
        self._tracker.reset()
        portal, self._portal = self._portal, None
        if portal is not None:
            portal.stop()

    def set_paused(self, paused):
        self._paused = bool(paused)

    def set_highlighting(self, on, rect=None):
        # Rect first: the loop reads it as soon as the flag is set.
        self._highlight_rect = rect if on else None
        # A new word, or none: evidence gathered for the old one no longer
        # applies.
        self._stale_hits = 0
        self._highlighting = bool(on)

    def set_region(self, region_str):
        # Boxes from the old capture area mean nothing in the new one.
        if region_str != self._region:
            self._tracker.reset()
        self._region = region_str

    def set_mask(self, rect):
        if rect != self._mask:
            self._mask_changed_at = time.monotonic()
        self._mask = rect

    @staticmethod
    def _signature(img):
        """Small greyscale thumbnail, cheap enough to compute every scan.

        Subsampled rather than resampled: no interpolation, just a stride, so
        the cost is a memory read. Coarse enough that a blinking cursor or a
        dithered gradient does not register, fine enough that a line of text
        appearing or changing does.
        """
        step = max(1, img.shape[1] // GATE_WIDTH)
        return img[::step, ::step].mean(axis=2)

    def _screen_moved_on(self, img):
        """Whether the screen changed under a highlight, not just the highlight.

        Compared against the last frame that was recognised, with the
        highlighted word and the popup left out: both are Fuwari's own
        drawing, and both change while the user is simply reading.
        """
        if self._last_sig is None:
            return False
        sig = self._signature(img)
        if sig.shape != self._last_sig.shape:
            return True
        diff = abs(sig - self._last_sig)
        step = max(1, img.shape[1] // GATE_WIDTH)
        pad = 2
        excluded = []
        if self._highlight_rect is not None:
            x, y, w, h = self._highlight_rect
            excluded.append((x, y, x + w, y + h))
        if self._mask_px is not None:
            excluded.append(self._mask_px)
        if self._last_sig_mask is not None:
            excluded.append(self._last_sig_mask)
        for x0, y0, x1, y1 in excluded:
            tx0 = max(0, x0 // step - pad)
            ty0 = max(0, y0 // step - pad)
            tx1 = min(diff.shape[1], x1 // step + 1 + pad)
            ty1 = min(diff.shape[0], y1 // step + 1 + pad)
            diff[ty0:ty1, tx0:tx1] = 0
        return diff.mean() >= self._stale_epsilon

    def _text_moved_on(self, img):
        """Whether the text changed under a highlight, not just the pixels.

        Called only when _screen_moved_on already says the frame differs.
        On an animated background that is true every scan while the text
        sits still, so the frame is read to be sure. The highlighted word is
        blanked first, since its tint would be read as different text, which
        means the read is the old text minus that word. So it counts as the
        same screen if nearly all of what was read is in what was last sent.

        Only regions on a stable track are compared: the background's
        flickering false text would otherwise make every frame look new.
        A new line in the same place still lands on its old track, and reads
        differently.
        """
        last = self._last_fired
        if not last:
            return True
        if self._highlight_rect is not None:
            x, y, w, h = self._highlight_rect
            pad = 4
            img[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad] = 0
        regions = self._tracker.known(
            self._pipeline.process(img, self._min_char_conf))
        text = self._to_sentence(regions)
        if not text:
            return True
        matcher = difflib.SequenceMatcher(None, text, last, autojunk=False)
        found = sum(b.size for b in matcher.get_matching_blocks())
        return found / len(text) < SIMILARITY_THRESHOLD

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
        #
        # Stays output-local, because that is the space the overlay draws in.
        self._capture_origin = (x, y)
        self._capture_logical = (w, h)

        portal = self._portal
        if portal is not None:
            # The stream is the whole monitor, already output-local, so the
            # output origin that grim needs does not apply here.
            logical = None
            try:
                _, _, sw, sh, valid = self._layershell.screen_geometry()
                if valid:
                    logical = (sw, sh)
            except Exception as e:
                print("screen_geometry failed during capture:", e)
            img = portal.grab_region(x, y, w, h, logical)
        else:
            # grim works in global layout coordinates, but the selection came
            # from a layer surface anchored to our output and so is
            # output-local. On any monitor whose top-left is not (0, 0) the
            # two differ by exactly the output origin.
            ox, oy = 0, 0
            try:
                gx, gy, _, _, valid = self._layershell.screen_geometry()
                if valid:
                    ox, oy = gx, gy
            except Exception as e:
                print("screen_geometry failed during capture:", e)
            img = self._layershell.capture(x + ox, y + oy, w, h)
        self._mask_px = None
        if img is None or self._mask is None:
            return img
        mx, my, mw, mh = self._mask
        # The mask is output-local logical; the frame is capture-local
        # physical. Shift by the capture origin, then scale by the ratio the
        # compositor actually gave us rather than an assumed scale factor.
        sx = img.shape[1] / w
        sy = img.shape[0] / h
        x0 = max(0, int((mx - x) * sx))
        y0 = max(0, int((my - y) * sy))
        x1 = min(img.shape[1], int((mx - x + mw) * sx))
        y1 = min(img.shape[0], int((my - y + mh) * sy))
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 0
            self._mask_px = (x0, y0, x1, y1)
        return img

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
    def _char_size(region):
        """Median glyph size along the axis that stays constant: height for
        horizontal text, width for vertical."""
        sizes = sorted(c.box[2] if region.vertical else c.box[3]
                       for c in region.chars)
        return sizes[len(sizes) // 2]

    @staticmethod
    def _continues(prev, cur):
        """Whether cur is the next line of the same paragraph as prev."""
        if prev.vertical != cur.vertical:
            return False
        sp = OCRThread._char_size(prev)
        sc = OCRThread._char_size(cur)
        if sp <= 0 or sc <= 0:
            return False
        if max(sp, sc) / min(sp, sc) > LINE_SIZE_RATIO:
            return False
        size = (sp + sc) / 2
        px, py, pw, ph = prev.box
        cx, cy, cw, ch = cur.box
        if prev.vertical:
            # Next column sits to the left, tops lined up.
            gap = px - (cx + cw)
            align = abs(cy - py)
        else:
            # Next line sits below, left edges lined up.
            gap = cy - (py + ph)
            align = abs(cx - px)
        return (-0.3 * size <= gap <= LINE_GAP_MAX * size
                and align <= LINE_ALIGN_MAX * size)

    @staticmethod
    def _group_lines(ordered):
        """Merge lines that continue one another into one region.

        Each line is checked against the last line of every group so far, not
        just the line before it in reading order: two text areas side by side
        interleave in the sorted list, and this keeps them apart.

        Characters are concatenated in order, so text[i] and chars[i] stay the
        same glyph and everything downstream maps boxes to offsets unchanged.
        """
        groups = []
        for region in ordered:
            if not region.chars:
                continue
            for group in groups:
                if OCRThread._continues(group[-1], region):
                    group.append(region)
                    break
            else:
                groups.append([region])

        out = []
        for group in groups:
            if len(group) == 1:
                out.append(group[0])
                continue
            chars = [c for r in group for c in r.chars]
            x0 = min(r.box[0] for r in group)
            y0 = min(r.box[1] for r in group)
            x1 = max(r.box[0] + r.box[2] for r in group)
            y1 = max(r.box[1] + r.box[3] for r in group)
            out.append(TextRegion(
                text=''.join(c.char for c in chars),
                box=(x0, y0, x1 - x0, y1 - y0),
                vertical=group[0].vertical,
                confidence=sum(c.confidence for c in chars) / len(chars),
                chars=chars,
            ))
        return out

    @staticmethod
    def _blocks(ordered):
        """One (text, chars) pair per detected block, kept apart.

        Lines that continue one another are merged into blocks by
        _group_lines first. Separate blocks are separate things -- a menu's
        アイテム and そうび are not a phrase -- so concatenating them would
        invent word boundaries that do not exist and produce a mined sentence
        containing the entire screen.

        Text is built from the character boxes rather than the block's own
        string, so text[i] and chars[i] are the same glyph by construction.
        """
        out = []
        for region in ordered:
            chars = region.chars or []
            if chars:
                out.append((''.join(c.char for c in chars), chars))
        return out

    @staticmethod
    def _joined(blocks):
        """What the word strip shows: blocks on their own lines."""
        return '\n'.join(text for text, _ in blocks)

    def _to_sentence(self, regions):
        ordered = self._order_regions(regions)
        grouped = self._group_lines(ordered) if self._join_lines else ordered
        return self._joined(self._blocks(grouped))

    def _loop(self):
        last_text = ""
        stable_count = 0
        while self._running:
            try:
                if self._paused or not self._region:
                    time.sleep(self._scan_interval)
                    continue
                # The popup is appearing, moving or going: wait until it has
                # settled, rather than capture a frame it may be half in.
                settle = MASK_SETTLE - (time.monotonic() - self._mask_changed_at)
                if settle > 0:
                    time.sleep(settle)
                    continue
                captured_at = time.monotonic()
                img = self._capture()
                if img is None:
                    time.sleep(self._scan_interval)
                    continue
                # It moved while the frame was being taken: same reason.
                if self._mask_changed_at >= captured_at:
                    continue
                # While a word is highlighted, the frame has Fuwari's own tint
                # in it, so it is never recognised. But the screen can still
                # move on underneath (the game advancing while the pointer
                # rests on a word), and pausing outright left the overlay
                # stuck on the old screen's words until the pointer left them.
                if self._highlighting:
                    if self._screen_moved_on(img) and self._text_moved_on(img):
                        self._stale_hits += 1
                    else:
                        self._stale_hits = 0
                    # Two scans in a row: a real change of screen stays
                    # changed, the popup's unmasked first frame does not.
                    if self._stale_hits >= 2:
                        self._stale_hits = 0
                        print("screen changed under the highlight; dropping it")
                        # Whatever comes next must reach the bridge, even if
                        # it reads the same as what was sent before, since
                        # the bridge is about to throw its boxes away.
                        self._last_fired = ""
                        if self._on_stale:
                            self._on_stale()
                    time.sleep(self._scan_interval)
                    continue

                sig = self._signature(img)
                self._scans += 1
                if (self._last_sig is not None
                        and abs(sig - self._last_sig).mean() < GATE_EPSILON):
                    # Identical pixels, so the text cannot have changed. That
                    # is a stronger guarantee than re-running OCR and
                    # comparing the strings, and it counts toward stability
                    # without paying for the recognition.
                    if self._held_back:
                        # Same pixels, so detection would find the same
                        # boxes: count that as their second sighting. Anything
                        # that passes now held still across two frames, which
                        # is what stable_count >= 2 stands for, so it can be
                        # sent on this scan rather than waiting another.
                        kept = self._tracker.update(self._last_raw)
                        self._held_back = len(kept) < len(self._last_raw)
                        ordered = self._order_regions(kept)
                        grouped = (self._group_lines(ordered)
                                   if self._join_lines else ordered)
                        self._last_regions = ordered
                        self._last_blocks = self._blocks(grouped)
                        text = self._joined(self._last_blocks)
                        if text:
                            last_text = text
                            stable_count = 1
                    if last_text:
                        stable_count += 1
                        if stable_count >= 2 and last_text != self._last_fired:
                            self._last_fired = last_text
                            self._callback(last_text)
                            if self._on_geometry:
                                self._on_geometry(self._last_blocks,
                                                  self._capture_origin,
                                                  self._capture_logical, img)
                    time.sleep(self._scan_interval)
                    continue
                self._last_sig = sig
                self._last_sig_mask = self._mask_px

                self._recognitions += 1
                t0 = time.perf_counter()
                regions = self._pipeline.process(img, self._min_char_conf)
                print(f"OCR pass #{self._recognitions} "
                      f"({(time.perf_counter() - t0) * 1000:.0f}ms) "
                      f"| scans: {self._scans} "
                      f"| mask: {'on' if self._mask else 'off'}")
                detected = len(regions)
                self._last_raw = regions
                regions = self._tracker.update(regions)
                self._held_back = len(regions) < detected
                if detected != len(regions):
                    print(f"  stability filter kept {len(regions)}/{detected} regions")
                ordered = self._order_regions(regions)
                grouped = self._group_lines(ordered) if self._join_lines else ordered
                blocks = self._blocks(grouped)
                text = self._joined(blocks)
                self._last_regions = ordered
                self._last_blocks = blocks
                if not text:
                    stable_count = 0
                    last_text = ""
                    time.sleep(self._scan_interval)
                    continue
                ratio = difflib.SequenceMatcher(None, last_text, text).ratio()
                if ratio >= SIMILARITY_THRESHOLD:
                    stable_count += 1
                else:
                    stable_count = 1
                last_text = text
                if stable_count >= 2 and text != self._last_fired:
                    self._last_fired = text
                    self._callback(text)
                    if self._on_geometry:
                        self._on_geometry(blocks, self._capture_origin,
                                          self._capture_logical, img)
            except Exception as e:
                print(f"OCR error: {e}")
            time.sleep(self._scan_interval)
