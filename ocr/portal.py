"""Screen capture through the ScreenCast portal.

For compositors without wlr-screencopy (KWin, Mutter), grim has nothing to
talk to. The portal instead hands back a PipeWire stream of a whole monitor,
after the user approves it once.

Frames only arrive when the screen changes, so the newest one is kept and
handed out again while the screen is still. The OCR loop's frame gate already
expects a still screen to repeat itself, so this costs nothing downstream.
"""
from __future__ import annotations

import os
import secrets
import threading
import time

import numpy as np

# Optional: only KWin and Mutter need the portal, and PyGObject plus the
# GStreamer typelibs are not installed everywhere. Failing here would take OCR
# down on wlroots compositors, where none of this is used.
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gio, GLib, Gst
    _GI_ERROR = None
except (ImportError, ValueError) as e:
    Gio = GLib = Gst = None
    _GI_ERROR = e

BUS_NAME = 'org.freedesktop.portal.Desktop'
OBJECT_PATH = '/org/freedesktop/portal/desktop'
SCREENCAST = 'org.freedesktop.portal.ScreenCast'
REQUEST = 'org.freedesktop.portal.Request'
SESSION = 'org.freedesktop.portal.Session'

SOURCE_MONITOR = 1
# The pointer sits over the text being read, and would be recognised as part
# of it.
CURSOR_HIDDEN = 1
PERSIST_UNTIL_REVOKED = 2

# Every call but Start answers at once; Start waits on the user.
QUICK_TIMEOUT = 10.0
DIALOG_TIMEOUT = 120.0
FIRST_FRAME_TIMEOUT = 3.0

# Kept apart from settings.json: the QML settings window saves that whole file
# from its own copy, which would drop a token written here in the meantime.
TOKEN_PATH = os.path.expanduser('~/.local/share/fuwari/portal_restore_token')


class PortalCancelled(Exception):
    """The user closed the share dialog."""


class PortalError(Exception):
    pass


class PortalWrongSource(PortalError):
    """The user shared something other than the whole screen Fuwari is on.

    KDE's dialog also offers a rectangular region, and any multi-monitor
    setup offers the other screens. The OCR region is picked by Fuwari and
    cropped out of this stream, so either choice breaks it.
    """
    def __init__(self, got, expected):
        super().__init__(f"shared {got[0]}x{got[1]}, "
                         f"but the screen is {expected[0]}x{expected[1]}")
        self.got = got
        self.expected = expected


def portal_needed() -> bool:
    """Whether this session has to capture through the portal.

    KWin and Mutter implement neither wlr-screencopy nor ext-image-copy-capture,
    which is everything grim can use.
    """
    if not os.getenv('WAYLAND_DISPLAY'):
        return False
    desktop = os.getenv('XDG_CURRENT_DESKTOP', '').upper()
    return 'KDE' in desktop or 'GNOME' in desktop


def _load_token() -> str:
    try:
        with open(TOKEN_PATH) as f:
            return f.read().strip()
    except OSError:
        return ''


def _save_token(token: str) -> None:
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, 'w') as f:
            f.write(token)
    except OSError as e:
        print("could not save portal restore token:", e)


def forget_selection() -> bool:
    """Drop the remembered screen, so the next start asks again.

    Returns whether there was anything to forget.
    """
    try:
        os.remove(TOKEN_PATH)
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        print("could not remove portal restore token:", e)
        return False


def _same_size(a, b, slack=2) -> bool:
    # A pixel or two either way is rounding in a fractional scale, not a
    # different source.
    return abs(a[0] - b[0]) <= slack and abs(a[1] - b[1]) <= slack


def _new_token() -> str:
    # Must be a valid object path element: letters, digits and underscores.
    return 'fuwari_' + secrets.token_hex(8)


class PortalCapture:
    def __init__(self):
        self._conn = None
        self._session = None
        self._pipeline = None
        self._sink = None
        self._frame = None
        self._stream_size = None
        self._lock = threading.Lock()
        self._reported = False

    # --- setup ---------------------------------------------------------------

    def start(self, expected_size=None) -> None:
        """Ask for the screen, then start receiving frames.

        Blocks until the user answers the share dialog, so call it off the Qt
        thread. Raises PortalCancelled if they close it, and PortalWrongSource
        if what they shared does not match expected_size, the logical size of
        the screen Fuwari is on. The bad choice is forgotten before raising,
        so asking again shows the dialog rather than restoring it.
        """
        if Gst is None:
            raise PortalError(
                f"screen capture needs PyGObject and GStreamer ({_GI_ERROR}); "
                "install python-gobject, gstreamer, gst-plugins-base and "
                "gst-plugin-pipewire")
        Gst.init(None)
        # The Response signals are delivered to the main context that was the
        # thread's default when they were subscribed to, so this thread gets
        # its own and pumps it while waiting.
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node, props = self._handshake(ctx)
        finally:
            ctx.pop_thread_default()

        size = props.get('size')
        if size and len(size) == 2 and size[0] > 0 and size[1] > 0:
            self._stream_size = (int(size[0]), int(size[1]))
        print(f"portal: stream node {node}, properties {props}")

        if (expected_size and self._stream_size
                and not _same_size(self._stream_size, expected_size)):
            got = self._stream_size
            forget_selection()
            self.stop()
            raise PortalWrongSource(got, tuple(expected_size))

        fd = self._open_remote()
        self._start_pipeline(fd, node)

        deadline = time.monotonic() + FIRST_FRAME_TIMEOUT
        while self._frame is None and time.monotonic() < deadline:
            self._pull_latest()
            if self._frame is None:
                time.sleep(0.02)
        if self._frame is None:
            raise PortalError("stream started but no frame arrived")

    def _sender(self) -> str:
        return self._conn.get_unique_name()[1:].replace('.', '_')

    def _subscribe(self, path, result):
        def on_response(_conn, _sender, _path, _iface, _signal, params):
            code, results = params.unpack()
            result['code'] = code
            result['results'] = results
        return self._conn.signal_subscribe(
            BUS_NAME, REQUEST, 'Response', path, None,
            Gio.DBusSignalFlags.NONE, on_response)

    def _request(self, ctx, method, arg_sig, args, options, timeout):
        """One portal call and its answer.

        The answer comes later, as a Response signal on a request object, and
        the portal can send it before the call has even returned. So the path
        is predicted from our own handle_token and subscribed to first.
        """
        token = _new_token()
        options = dict(options)
        options['handle_token'] = GLib.Variant('s', token)
        expected = f'{OBJECT_PATH}/request/{self._sender()}/{token}'

        result = {}
        sub = self._subscribe(expected, result)
        try:
            reply = self._conn.call_sync(
                BUS_NAME, OBJECT_PATH, SCREENCAST, method,
                GLib.Variant(f'({arg_sig}a{{sv}})', (*args, options)),
                GLib.VariantType('(o)'), Gio.DBusCallFlags.NONE, -1, None)
            handle = reply.unpack()[0]
            if handle != expected and 'code' not in result:
                # Portals older than 0.9 ignore handle_token and pick their
                # own path.
                self._conn.signal_unsubscribe(sub)
                sub = self._subscribe(handle, result)

            deadline = time.monotonic() + timeout
            while 'code' not in result:
                if time.monotonic() > deadline:
                    raise PortalError(f"{method}: no response from the portal")
                if not ctx.iteration(False):
                    time.sleep(0.01)
        finally:
            self._conn.signal_unsubscribe(sub)

        code = result['code']
        if code == 1:
            raise PortalCancelled()
        if code != 0:
            raise PortalError(f"{method} failed (response {code})")
        return result['results']

    def _handshake(self, ctx):
        res = self._request(
            ctx, 'CreateSession', '', (),
            {'session_handle_token': GLib.Variant('s', _new_token())},
            QUICK_TIMEOUT)
        self._session = res['session_handle']

        opts = {
            'types': GLib.Variant('u', SOURCE_MONITOR),
            'multiple': GLib.Variant('b', False),
            'cursor_mode': GLib.Variant('u', CURSOR_HIDDEN),
            'persist_mode': GLib.Variant('u', PERSIST_UNTIL_REVOKED),
        }
        token = _load_token()
        if token:
            opts['restore_token'] = GLib.Variant('s', token)
        self._request(ctx, 'SelectSources', 'o', (self._session,), opts,
                      QUICK_TIMEOUT)

        res = self._request(ctx, 'Start', 'os', (self._session, ''), {},
                            DIALOG_TIMEOUT)
        # Single use: every session hands back a fresh one, and only that one
        # will restore the next.
        new_token = res.get('restore_token')
        if new_token:
            _save_token(new_token)

        streams = res.get('streams') or []
        if not streams:
            raise PortalError("portal returned no streams")
        node, props = streams[0]
        return int(node), dict(props)

    def _open_remote(self) -> int:
        reply, fds = self._conn.call_with_unix_fd_list_sync(
            BUS_NAME, OBJECT_PATH, SCREENCAST, 'OpenPipeWireRemote',
            GLib.Variant('(oa{sv})', (self._session, {})),
            GLib.VariantType('(h)'), Gio.DBusCallFlags.NONE, -1, None, None)
        return fds.get(reply.unpack()[0])

    def _start_pipeline(self, fd, node):
        # The four packed formats are what compositors actually send, so
        # videoconvert normally passes straight through. Channel order is
        # fixed up in numpy, only for the frames that are used, rather than
        # converting every frame the compositor sends.
        desc = (
            f'pipewiresrc fd={fd} path={node} always-copy=true ! '
            'videoconvert ! '
            'video/x-raw,format=(string){BGRx,BGRA,RGBx,RGBA} ! '
            'appsink name=sink max-buffers=1 drop=true sync=false'
        )
        self._pipeline = Gst.parse_launch(desc)
        self._sink = self._pipeline.get_by_name('sink')
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise PortalError("GStreamer pipeline would not start")

    # --- frames --------------------------------------------------------------

    def _pull_latest(self) -> None:
        """Replace the kept frame if a newer one has arrived. Never blocks."""
        sink = self._sink
        if sink is None:
            return
        sample = sink.emit('try-pull-sample', 0)
        if sample is None:
            return
        s = sample.get_caps().get_structure(0)
        w, h = s.get_value('width'), s.get_value('height')
        fmt = s.get_value('format')
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return
        try:
            data = np.frombuffer(info.data, dtype=np.uint8)
            # Rows can be padded, so the stride comes from the buffer rather
            # than from the width.
            stride = info.size // h
            px = data[:stride * h].reshape(h, stride)[:, :w * 4].reshape(h, w, 4)
            rgb = px[:, :, 2::-1] if fmt.startswith('BGR') else px[:, :, :3]
            frame = np.ascontiguousarray(rgb)
        finally:
            buf.unmap(info)
        with self._lock:
            self._frame = frame

    def grab_region(self, x, y, w, h, logical_size=None):
        """The selected region out of the newest frame, as RGB.

        x, y, w, h are output-local logical pixels, which is how the region
        was selected. The frame is in physical pixels, so the scale is
        measured from its width against the monitor's logical width.
        """
        self._pull_latest()
        with self._lock:
            frame = self._frame
        if frame is None:
            return None
        fh, fw = frame.shape[0], frame.shape[1]
        lw, lh = logical_size or self._stream_size or (fw, fh)
        if lw <= 0 or lh <= 0:
            return None
        sx, sy = fw / lw, fh / lh
        if not self._reported:
            self._reported = True
            print(f"portal: frame {fw}x{fh}, logical {lw}x{lh}, "
                  f"stream size {self._stream_size}, scale {sx:.3f}x{sy:.3f}")
        x0 = max(0, int(x * sx))
        y0 = max(0, int(y * sy))
        x1 = min(fw, int((x + w) * sx))
        y1 = min(fh, int((y + h) * sy))
        if x1 <= x0 or y1 <= y0:
            return None
        # A copy: the OCR loop blanks the popup mask into what it is given,
        # and the same frame may be handed out again next scan.
        return frame[y0:y1, x0:x1].copy()

    # --- teardown ------------------------------------------------------------

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._sink = None
        if self._conn is not None and self._session:
            try:
                self._conn.call_sync(
                    BUS_NAME, self._session, SESSION, 'Close', None, None,
                    Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error as e:
                print("portal session close failed:", e)
            self._session = None
