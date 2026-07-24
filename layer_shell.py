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
