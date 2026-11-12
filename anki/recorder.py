"""Rolling buffer of desktop audio, for sentence audio on Anki cards.

pw-record captures whatever is going to the speakers (stream.capture.sink) as
raw mono 16-bit samples, and a reader thread copies them into a fixed-size
numpy ring. Nothing touches the disk until a card asks for a clip, so the cost
while it runs is the ring itself (about 96 KB per second of buffer) plus the
pw-record process.

Also home to the media cache that screenshots and clips are written to before
AnkiConnect copies them into the collection.
"""
import atexit
import os
import shutil
import subprocess
import threading
import time
import wave

import numpy as np

RATE = 48000
MIN_SECONDS = 5
MAX_SECONDS = 60
# Read in 100 ms pieces: small enough that a snapshot is never more than a
# tenth of a second behind, large enough that the thread is mostly asleep.
CHUNK_SAMPLES = RATE // 10

MEDIA_DIR = os.path.expanduser('~/.cache/fuwari/media')
# Files older than this are left over from earlier cards: AnkiConnect has
# already copied whatever was added, so they are only taking up space.
MEDIA_MAX_AGE = 60 * 60


def clamp_seconds(seconds):
    try:
        seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        seconds = 20
    return max(MIN_SECONDS, min(MAX_SECONDS, seconds))


def new_media_path(ext):
    """A fresh file name in the media cache, clearing out stale ones first."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    now = time.time()
    for name in os.listdir(MEDIA_DIR):
        path = os.path.join(MEDIA_DIR, name)
        try:
            if now - os.path.getmtime(path) > MEDIA_MAX_AGE:
                os.remove(path)
        except OSError:
            pass
    return os.path.join(MEDIA_DIR, f"fuwari_{int(now * 1000)}{ext}")


def _supports_raw_flag(pw_record):
    """Whether this pw-record takes --raw.

    Newer PipeWire writes a self-describing .au stream to stdout unless told
    --raw; older releases have no such flag and write raw samples anyway. The
    help text is the one way to tell them apart without guessing at versions.
    """
    try:
        out = subprocess.run([pw_record, '--help'], capture_output=True,
                             text=True, timeout=5)
        return '--raw' in (out.stdout + out.stderr)
    except Exception:
        return False


class AudioBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._ring = None
        self._pos = 0          # next sample to write
        self._filled = False   # whether the ring has wrapped at least once
        self._proc = None
        self._thread = None
        self._running = False
        atexit.register(self.stop)

    @property
    def running(self):
        return self._running

    def start(self, seconds):
        """Start buffering, or resize a buffer that is already running."""
        seconds = clamp_seconds(seconds)
        if self._running:
            self.resize(seconds)
            return True

        pw_record = shutil.which('pw-record')
        if pw_record is None:
            print("sentence audio: pw-record not found; is PipeWire installed?")
            return False

        cmd = [pw_record]
        if _supports_raw_flag(pw_record):
            cmd.append('--raw')
        cmd += [
            '--rate', str(RATE),
            '--channels', '1',
            '--format', 's16',
            # Capture the sink's monitor (what is being played), not a mic.
            '-P', '{"stream.capture.sink": true, '
                  '"node.name": "fuwari-sentence-audio", '
                  '"node.description": "Fuwari sentence audio"}',
            '-',
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
        except OSError as e:
            print(f"sentence audio: could not start pw-record: {e}")
            return False

        with self._lock:
            self._ring = np.zeros(seconds * RATE, dtype=np.int16)
            self._pos = 0
            self._filled = False
        self._proc = proc
        self._running = True
        self._thread = threading.Thread(target=self._read, args=(proc,),
                                        daemon=True)
        self._thread.start()
        print(f"sentence audio: buffering the last {seconds}s")
        return True

    def stop(self):
        self._running = False
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        with self._lock:
            # Freed rather than kept, so turning the toggle off gives the
            # memory back.
            self._ring = None
            self._pos = 0
            self._filled = False

    def resize(self, seconds):
        """Change the length, keeping as much of the newest audio as fits."""
        seconds = clamp_seconds(seconds)
        with self._lock:
            if self._ring is None or len(self._ring) == seconds * RATE:
                return
            old = self._ordered_locked()
            ring = np.zeros(seconds * RATE, dtype=np.int16)
            keep = old[-len(ring):]
            ring[:len(keep)] = keep
            self._ring = ring
            self._pos = len(keep) % len(ring)
            self._filled = len(keep) == len(ring)
        print(f"sentence audio: buffer is now {seconds}s")

    def snapshot(self):
        """The buffered audio, oldest first, as a copy that will not change.

        None when the buffer is off or has not received anything yet.
        """
        with self._lock:
            if self._ring is None:
                return None
            clip = self._ordered_locked()
        return clip if len(clip) else None

    # -- internals ------------------------------------------------------------

    def _ordered_locked(self):
        if self._filled:
            return np.concatenate((self._ring[self._pos:], self._ring[:self._pos]))
        return self._ring[:self._pos].copy()

    def _push(self, samples):
        with self._lock:
            ring = self._ring
            if ring is None:
                return
            n = len(ring)
            if len(samples) >= n:
                ring[:] = samples[-n:]
                self._pos = 0
                self._filled = True
                return
            end = self._pos + len(samples)
            if end <= n:
                ring[self._pos:end] = samples
            else:
                first = n - self._pos
                ring[self._pos:] = samples[:first]
                ring[:end - n] = samples[first:]
                self._filled = True
            self._pos = end % n
            if end == n:
                self._filled = True

    def _read(self, proc):
        want = CHUNK_SAMPLES * 2
        leftover = b''
        while self._running:
            data = proc.stdout.read(want)
            if not data:
                break
            data = leftover + data
            # A read can end halfway through a sample; carry the odd byte over.
            if len(data) % 2:
                data, leftover = data[:-1], data[-1:]
            else:
                leftover = b''
            self._push(np.frombuffer(data, dtype='<i2'))
        if self._running:
            print("sentence audio: pw-record stopped unexpectedly")
            self._running = False


def clip_peaks(clip, count):
    """One value per bar of the waveform, 0..1, scaled to the loudest bar.

    The max of each slice rather than an average: an average flattens speech
    into the noise floor, while the max keeps every syllable visible.
    """
    if clip is None or len(clip) == 0 or count <= 0:
        return []
    count = min(count, len(clip))
    per = len(clip) // count
    bars = np.abs(clip[:per * count].astype(np.int32)).reshape(count, per).max(axis=1)
    top = bars.max()
    if top <= 0:
        return [0.0] * count
    return (bars / top).astype(float).tolist()


def export_clip(clip, start_frac, end_frac):
    """Write the selected part of a clip to the media cache.

    Opus through ffmpeg when it is installed, since a WAV sentence is about
    ten times the size; plain WAV otherwise, which Anki plays just as well.
    Returns the file path, or "" when the selection is empty.
    """
    if clip is None or len(clip) == 0:
        return ""
    start_frac = max(0.0, min(1.0, float(start_frac)))
    end_frac = max(0.0, min(1.0, float(end_frac)))
    a, b = int(start_frac * len(clip)), int(end_frac * len(clip))
    if b - a < RATE // 20:   # under 50 ms is a mis-drag, not a sentence
        return ""
    part = clip[a:b]

    wav_path = new_media_path('.wav')
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(part.astype('<i2').tobytes())

    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        return wav_path
    opus_path = wav_path[:-4] + '.opus'
    result = subprocess.run(
        [ffmpeg, '-y', '-loglevel', 'error', '-i', wav_path,
         '-c:a', 'libopus', '-b:a', '48k', opus_path],
        capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(opus_path):
        print(f"sentence audio: ffmpeg failed, keeping WAV: {result.stderr.strip()}")
        return wav_path
    os.remove(wav_path)
    return opus_path
