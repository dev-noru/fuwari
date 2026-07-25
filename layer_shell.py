import ctypes
import os
import time
import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
lib = ctypes.CDLL(os.path.join(
    _here, "fuwari-layer-shell", "target", "release", "libfuwari_layer_shell.so"
))

# handle is stored as c_uint64 rather than c_void_p due to a Python 3.14
# regression in c_void_p pointer round-tripping across FFI boundaries
lib.fuwari_start.restype = ctypes.c_uint64
lib.fuwari_start.argtypes = []
lib.fuwari_shutdown.restype = None
lib.fuwari_shutdown.argtypes = [ctypes.c_uint64]
lib.fuwari_free.restype = None
lib.fuwari_free.argtypes = [ctypes.c_uint64]

lib.fuwari_show.restype = None
lib.fuwari_show.argtypes = [ctypes.c_uint64]
lib.fuwari_hide.restype = None
lib.fuwari_hide.argtypes = [ctypes.c_uint64]

lib.fuwari_start_region_select.restype = None
lib.fuwari_start_region_select.argtypes = [ctypes.c_uint64]
lib.fuwari_stop_region_select.restype = None
lib.fuwari_stop_region_select.argtypes = [ctypes.c_uint64]
lib.fuwari_poll_region.restype = ctypes.c_char_p
lib.fuwari_poll_region.argtypes = [ctypes.c_uint64]

lib.fuwari_start_drag.restype = None
lib.fuwari_start_drag.argtypes = [
    ctypes.c_uint64,                                    # handle
    ctypes.c_int32, ctypes.c_int32,                     # x, y
    ctypes.c_int32, ctypes.c_int32,                     # width, height
    ctypes.c_int32, ctypes.c_int32,                     # grab_x, grab_y
]
lib.fuwari_set_drag_style.restype = None
lib.fuwari_set_drag_style.argtypes = [
    ctypes.c_uint64,                                    # handle
    ctypes.c_uint32,                                    # rgb, packed 0xRRGGBB
    ctypes.c_int32,                                     # border
    ctypes.c_int32,                                     # radius
    ctypes.c_int32,                                     # fill_pct
]
lib.fuwari_stop_drag.restype = None
lib.fuwari_stop_drag.argtypes = [ctypes.c_uint64]
lib.fuwari_poll_drag.restype = ctypes.c_char_p
lib.fuwari_poll_drag.argtypes = [ctypes.c_uint64]

def _bind(name, restype, argtypes):
    """Bind an optional symbol, tolerating a library older than this file.

    ctypes resolves symbols on attribute access, so a missing one raises at
    module scope and takes every feature down with it, including ones that
    have nothing to do with it. Returning None instead confines the damage to
    the feature that needs the symbol.
    """
    try:
        fn = getattr(lib, name)
    except AttributeError:
        print(f"fuwari: {name} is missing from libfuwari_layer_shell.so; "
              f"rebuild it with 'cd fuwari-layer-shell && cargo build --release'")
        return None
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


class Region(ctypes.Structure):
    """Mirrors types::Region. Lengths are compositor logical pixels."""
    _fields_ = [
        ("x", ctypes.c_int32),
        ("y", ctypes.c_int32),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("index", ctypes.c_size_t),
    ]


_set_regions = _bind("fuwari_set_regions", None, [
    ctypes.c_uint64,                    # handle
    ctypes.POINTER(Region),             # regions
    ctypes.c_size_t,                    # count
])
_poll_hover = _bind("fuwari_poll_hover", ctypes.c_int64, [ctypes.c_uint64])
_set_debug_boxes = _bind("fuwari_set_debug_boxes", None, [
    ctypes.c_uint64,                    # handle
    ctypes.c_int32,                     # on
    ctypes.c_uint32,                    # rgb, packed 0xRRGGBB
])

lib.fuwari_screen_size.restype = None
lib.fuwari_screen_size.argtypes = [
    ctypes.c_uint64,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(ctypes.c_uint32),
]

lib.fuwari_capture.restype = ctypes.POINTER(ctypes.c_ubyte)
lib.fuwari_capture.argtypes = [
    ctypes.c_uint64,                    # handle
    ctypes.c_int32, ctypes.c_int32,     # x, y
    ctypes.c_int32, ctypes.c_int32,     # width, height
    ctypes.POINTER(ctypes.c_uint32),    # out_w
    ctypes.POINTER(ctypes.c_uint32),    # out_h
]


class LayerShell:
    def __init__(self) -> None:
        self.handle = ctypes.c_uint64(lib.fuwari_start())

    def shutdown(self):
        lib.fuwari_shutdown(self.handle)
        lib.fuwari_free(self.handle)
        self.handle = None

    def show(self):
        lib.fuwari_show(self.handle)

    def hide(self):
        lib.fuwari_hide(self.handle)

    def screen_size(self):
        """(width, height) in compositor logical pixels, or (0, 0) if the
        Wayland thread has not seen an output yet."""
        w = ctypes.c_uint32(0)
        h = ctypes.c_uint32(0)
        lib.fuwari_screen_size(self.handle, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def capture(self, x, y, w, h):
        out_w = ctypes.c_uint32(0)
        out_h = ctypes.c_uint32(0)
        ptr = lib.fuwari_capture(self.handle, x, y, w, h,
                                 ctypes.byref(out_w), ctypes.byref(out_h))
        if not ptr:
            return None
        cw, ch = out_w.value, out_h.value
        n = cw * ch * 4
        buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * n)).contents
        rgba = np.frombuffer(buf, dtype=np.uint8).reshape((ch, cw, 4))
        return rgba[:, :, :3].copy()

    # --- OCR overlay ---

    def set_regions(self, regions):
        """regions: iterable of (x, y, width, height, index), logical pixels.

        The union of these rectangles becomes the surface's input region, so
        the overlay is transparent to the pointer everywhere else. index is
        carried back on hover and click, and several rectangles may share one
        index when a token spans several characters.
        """
        if _set_regions is None:
            return
        regions = list(regions)
        if not regions:
            _set_regions(self.handle, None, 0)
            return
        arr = (Region * len(regions))()
        for slot, (x, y, w, h, index) in zip(arr, regions):
            slot.x, slot.y = int(x), int(y)
            slot.width, slot.height = int(w), int(h)
            slot.index = int(index)
        _set_regions(self.handle, arr, len(regions))

    def poll_hover(self):
        """Region index under the pointer, -1 once it has left them all, or
        -2 if nothing changed since the last call."""
        if _poll_hover is None:
            return -2
        return int(_poll_hover(self.handle))

    def set_debug_boxes(self, on, rgb=0x00FF00):
        """Outline every region, to check placement against the glyphs."""
        if _set_debug_boxes is None:
            return
        _set_debug_boxes(self.handle, 1 if on else 0, int(rgb) & 0xFFFFFF)

    def select_region(self, timeout=30.0):
        lib.fuwari_start_region_select(self.handle)
        deadline = time.time() + timeout
        while time.time() < deadline:
            ptr = lib.fuwari_poll_region(self.handle)
            if ptr:
                return ptr.decode("utf-8")
            time.sleep(0.05)
        lib.fuwari_stop_region_select(self.handle)
        return None

    # --- window drag ---
    #
    # Non-blocking, unlike select_region: the caller drives poll_drag from a
    # QTimer so the Qt event loop keeps running while the ghost is on screen.

    def set_drag_style(self, rgb, border, radius, fill_pct):
        lib.fuwari_set_drag_style(self.handle, int(rgb) & 0xFFFFFF,
                                  int(border), int(radius), int(fill_pct))

    def start_drag(self, x, y, w, h, grab_x, grab_y):
        lib.fuwari_start_drag(self.handle, int(x), int(y), int(w), int(h),
                              int(grab_x), int(grab_y))

    def poll_drag(self):
        """Returns "x,y" on drop, "cancel" if aborted, or None if still dragging."""
        ptr = lib.fuwari_poll_drag(self.handle)
        if not ptr:
            return None
        return ptr.decode("utf-8")

    def stop_drag(self):
        lib.fuwari_stop_drag(self.handle)
