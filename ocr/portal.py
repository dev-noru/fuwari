"""Screen capture through the ScreenCast portal.

For compositors without wlr-screencopy (KWin, Mutter), grim has nothing to
talk to. The portal instead hands back a PipeWire stream of a whole monitor,
after the user approves it once.

No PyGObject: it only installs by compiling against the system's GObject
libraries, so it cannot be bundled in the AppImage. The portal handshake uses
jeepney, a pure-Python D-Bus library, and frames come from the system's own
GStreamer run as a helper process, writing raw pixels down a pipe. Only that
helper needs anything from the system, and only on desktops that use the
portal at all.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import threading
import time

import numpy as np

try:
    from jeepney import (DBusAddress, MatchRule, MessageType, message_bus,
                         new_method_call)
    from jeepney.io.blocking import Proxy, open_dbus_connection
    _JEEPNEY_ERROR = None
except ImportError as e:
    _JEEPNEY_ERROR = e

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
FIRST_FRAME_TIMEOUT = 5.0

# Frames per second the helper passes on. Fuwari only looks at the newest
# frame when it scans, so anything beyond that is thrown away inside the
# helper instead of being copied down the pipe. Four keeps a fresh frame ready
# even on the Fast scan setting (every 0.25s).
HELPER_MAX_FPS = 4

# The GStreamer elements the helper pipeline uses, checked before starting so
# a missing plugin gives a clear message rather than a stalled capture.
REQUIRED_ELEMENTS = ('pipewiresrc', 'videorate', 'videoconvert', 'fdsink')

# Kept apart from settings.json: the QML settings window saves that whole file
# from its own copy, which would drop a token written here in the meantime.
TOKEN_PATH = os.path.expanduser('~/.local/share/fuwari/portal_restore_token')

# What to tell someone whose system lacks GStreamer or its PipeWire plugin.
INSTALL_HINT = (
    "OCR on this desktop needs GStreamer and its PipeWire plugin. Install "
    "them with your package manager: on Arch and CachyOS, gstreamer, "
    "gst-plugins-base and gst-plugin-pipewire; on Debian and Ubuntu, "
    "gstreamer1.0-tools, gstreamer1.0-plugins-base and gstreamer1.0-pipewire; "
    "on Fedora, gstreamer1-plugins-base and pipewire-gstreamer."
)

# Environment variables the AppImage sets for its own bundled libraries. The
# helper is the system's GStreamer and must load the system's libraries, so
# these are removed for it: inheriting them would point it at the bundle's
# older copies.
_BUNDLE_ENV = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONHOME', 'PYTHONPATH',
               'GST_PLUGIN_PATH', 'GST_PLUGIN_PATH_1_0', 'GST_PLUGIN_SYSTEM_PATH',
               'GST_PLUGIN_SYSTEM_PATH_1_0', 'GST_PLUGIN_SCANNER',
               'GIO_MODULE_DIR', 'GI_TYPELIB_PATH')

# The helper's -v output names the caps it settled on, which is how the frame
# size is learned: raw pixels down a pipe carry no size of their own.
_CAPS_RE = re.compile(r'fdsink.*caps = video/x-raw.*?width=\(int\)(\d+).*?height=\(int\)(\d+)')


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


def _helper_env():
    env = dict(os.environ)
    for name in _BUNDLE_ENV:
        env.pop(name, None)
    return env


def _unwrap(value):
    """jeepney hands variants back as (signature, value) pairs; drop the
    signatures, all the way down, so results read like plain Python."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) \
            and value[0] and value[0][0] in 'abdghinoqstuvxy(':
        return _unwrap(value[1])
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_unwrap(v) for v in value)
    return value


def gstreamer_missing():
    """What the helper needs from the system and does not have, or None."""
    env = _helper_env()
    if not shutil.which('gst-launch-1.0', path=env.get('PATH')) \
            or not shutil.which('gst-inspect-1.0', path=env.get('PATH')):
        return "gst-launch-1.0 / gst-inspect-1.0"
    for element in REQUIRED_ELEMENTS:
        try:
            ok = subprocess.run(['gst-inspect-1.0', element], env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if not ok:
            return element
    return None


class PortalCapture:
    def __init__(self):
        self._conn = None
        self._session = None
        self._proc = None
        self._read_fd = None
        self._frame = None
        self._size = None            # (w, h) the helper is sending
        self._stream_size = None
        self._lock = threading.Lock()
        self._stderr_tail = []
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
        if _JEEPNEY_ERROR is not None:
            raise PortalError(f"screen capture needs the jeepney package ({_JEEPNEY_ERROR})")
        # Checked before the dialog, so nobody picks a screen only to be told
        # afterwards that capture cannot work.
        missing = gstreamer_missing()
        if missing:
            raise PortalError(f"{INSTALL_HINT} (missing: {missing})")

        self._conn = open_dbus_connection(bus='SESSION', enable_fds=True)
        node, props = self._handshake()

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
        self._start_helper(fd, node)

        deadline = time.monotonic() + FIRST_FRAME_TIMEOUT
        while self._frame is None and time.monotonic() < deadline:
            if self._proc.poll() is not None:
                break
            time.sleep(0.05)
        if self._frame is None:
            detail = ' '.join(self._stderr_tail[-3:]) or "no output"
            raise PortalError(f"screen share started but no frame arrived ({detail})")

    def _sender(self) -> str:
        return self._conn.unique_name[1:].replace('.', '_')

    def _call(self, method, signature, args, timeout=QUICK_TIMEOUT):
        msg = new_method_call(
            DBusAddress(OBJECT_PATH, bus_name=BUS_NAME, interface=SCREENCAST),
            method, signature, args)
        reply = self._conn.send_and_get_reply(msg, timeout=timeout)
        if reply.header.message_type == MessageType.error:
            raise PortalError(f"{method} failed: {reply.body}")
        return reply

    def _request(self, method, arg_sig, args, options, timeout):
        """One portal call and its answer.

        The answer comes later, as a Response signal on a request object, and
        the portal can send it before the call has even returned. So the path
        is predicted from our own handle_token and listened on first.
        """
        token = _new_token()
        options = dict(options)
        options['handle_token'] = ('s', token)
        expected = f'{OBJECT_PATH}/request/{self._sender()}/{token}'

        rule = MatchRule(type='signal', interface=REQUEST, member='Response',
                         path=expected)
        Proxy(message_bus, self._conn).AddMatch(rule)
        with self._conn.filter(rule) as queue:
            reply = self._call(method, arg_sig + 'a{sv}', (*args, options))
            handle = reply.body[0]
            if handle != expected:
                # Portals before 0.9 ignored handle_token. Long gone from any
                # current desktop, so not worth a second code path.
                raise PortalError("the screen-share portal is too old")
            try:
                response = self._conn.recv_until_filtered(queue, timeout=timeout)
            except TimeoutError:
                raise PortalError(f"{method}: no response from the portal")

        code, results = response.body
        if code == 1:
            raise PortalCancelled()
        if code != 0:
            raise PortalError(f"{method} failed (response {code})")
        return _unwrap(results)

    def _handshake(self):
        res = self._request(
            'CreateSession', '', (),
            {'session_handle_token': ('s', _new_token())},
            QUICK_TIMEOUT)
        self._session = res['session_handle']

        opts = {
            'types': ('u', SOURCE_MONITOR),
            'multiple': ('b', False),
            'cursor_mode': ('u', CURSOR_HIDDEN),
            'persist_mode': ('u', PERSIST_UNTIL_REVOKED),
        }
        token = _load_token()
        if token:
            opts['restore_token'] = ('s', token)
        self._request('SelectSources', 'o', (self._session,), opts,
                      QUICK_TIMEOUT)

        res = self._request('Start', 'os', (self._session, ''), {},
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
        reply = self._call('OpenPipeWireRemote', 'oa{sv}', (self._session, {}))
        return reply.body[0].to_raw_fd()

    def _start_helper(self, fd, node):
        read_fd, write_fd = os.pipe()
        # RGBx rather than RGB: four bytes a pixel means rows are never padded,
        # so a frame is exactly width * height * 4 bytes on the pipe.
        pipeline = (
            f'pipewiresrc fd={fd} path={node} always-copy=true do-timestamp=true ! '
            f'videorate drop-only=true max-rate={HELPER_MAX_FPS} ! '
            'videoconvert ! video/x-raw,format=RGBx ! '
            f'fdsink fd={write_fd} sync=false'
        )
        # -v prints the caps each element settles on to stdout, which is
        # where the frame size comes from. The frames themselves go to the
        # pipe, so the two never mix.
        self._proc = subprocess.Popen(
            ['gst-launch-1.0', '-v'] + pipeline.split(),
            pass_fds=(fd, write_fd),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_helper_env(), text=False)
        # The helper has its own copies now. Ours would keep the pipe open
        # after the helper exits, so a reader would never see it end.
        os.close(write_fd)
        os.close(fd)
        self._read_fd = read_fd

        threading.Thread(target=self._read_caps, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        threading.Thread(target=self._read_frames, daemon=True).start()

    # --- helper output -------------------------------------------------------

    def _read_caps(self):
        for raw in self._proc.stdout:
            line = raw.decode('utf-8', 'replace')
            m = _CAPS_RE.search(line)
            if m:
                with self._lock:
                    self._size = (int(m.group(1)), int(m.group(2)))

    def _read_stderr(self):
        for raw in self._proc.stderr:
            line = raw.decode('utf-8', 'replace').strip()
            if line:
                self._stderr_tail = (self._stderr_tail + [line])[-10:]

    def _read_exact(self, n):
        buf = bytearray(n)
        view = memoryview(buf)
        got = 0
        while got < n:
            chunk = os.read(self._read_fd, n - got)
            if not chunk:
                return None              # helper exited
            view[got:got + len(chunk)] = chunk
            got += len(chunk)
        return buf

    def _read_frames(self):
        # Nothing on the pipe makes sense until the frame size is known.
        while self._size is None:
            if self._proc is None or self._proc.poll() is not None:
                return
            time.sleep(0.02)
        while True:
            with self._lock:
                w, h = self._size
            data = self._read_exact(w * h * 4)
            if data is None:
                return
            px = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
            frame = np.ascontiguousarray(px[:, :, :3])
            with self._lock:
                self._frame = frame

    def grab_region(self, x, y, w, h, logical_size=None):
        """The selected region out of the newest frame, as RGB.

        x, y, w, h are output-local logical pixels, which is how the region
        was selected. The frame is in physical pixels, so the scale is
        measured from its width against the monitor's logical width.
        """
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
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._read_fd is not None:
            try:
                os.close(self._read_fd)
            except OSError:
                pass
            self._read_fd = None
        if self._conn is not None:
            if self._session:
                try:
                    self._conn.send(new_method_call(
                        DBusAddress(self._session, bus_name=BUS_NAME,
                                    interface=SESSION), 'Close'))
                except Exception as e:
                    print("portal session close failed:", e)
                self._session = None
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
