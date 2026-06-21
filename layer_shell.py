import ctypes
lib = ctypes.CDLL("fuwari-layer-shell/target/debug/libfuwari_layer_shell.so")

# handle is stored as c_uint64 rather than c_void_p due to a Python 3.14
# regression in c_void_p pointer round-tripping across FFI boundaries

lib.fuwari_start.restype = ctypes.c_uint64
lib.fuwari_start.argtypes = []

lib.fuwari_shutdown.restype = None
lib.fuwari_shutdown.argtypes = [ctypes.c_uint64]

lib.fuwari_free.restype = None
lib.fuwari_free.argtypes = [ctypes.c_uint64]

class LayerShell:
    def __init__(self) -> None:
        self.handle = ctypes.c_uint64(lib.fuwari_start())

    def shutdown(self):
        lib.fuwari_shutdown(self.handle)
        lib.fuwari_free(self.handle)
        lib.fuwari_show.restype = None
        lib.fuwari_show.argtypes = [ctypes.c_uint64]
        self.handle = None

    def show(self):
        lib.fuwari_show(self.handle)
