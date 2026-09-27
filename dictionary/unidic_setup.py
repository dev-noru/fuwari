"""UniDic, the dictionary MeCab splits sentences into words with.

Not bundled with the app: at 770MB it was most of the AppImage. It is
downloaded once into Fuwari's data folder instead. That folder lives outside
the AppImage, so it survives updates the same way imported Yomitan
dictionaries do, and nobody downloads it twice.
"""
import os
import shutil
import ssl
import urllib.request
import zipfile

# The same UniDic 3.1.0 build the `unidic` pip package installs, from that
# package's own host, so tokenizing stays exactly what Fuwari was tuned on.
UNIDIC_URL = 'https://cotonoha-dic.s3-ap-northeast-1.amazonaws.com/unidic-3.1.0.zip'
UNIDIC_VERSION = '3.1.0+2021-08-31'

DATA_DIR = os.path.expanduser('~/.local/share/fuwari')
UNIDIC_DIR = os.path.join(DATA_DIR, 'unidic')
# Scratch space for the zip and its contents. Inside DATA_DIR so the final
# move is a rename on the same disk, not a second 770MB copy.
_WORK_DIR = os.path.join(DATA_DIR, '.unidic-download')
# MeCab will not start without a config file, and an AppImage has none of the
# system's. An empty one is enough: everything it would set is passed as
# arguments instead.
_MECABRC = os.path.join(DATA_DIR, 'mecabrc')

# What MeCab actually reads to tokenize. model.bin is only for retraining.
REQUIRED = ('char.bin', 'dicrc', 'matrix.bin', 'sys.dic', 'unk.dic')

_CHUNK = 1 << 20   # 1MB


def _complete(path):
    return os.path.isdir(path) and all(
        os.path.isfile(os.path.join(path, f)) for f in REQUIRED)


def find_dicdir():
    """Where UniDic is, or None if it hasn't been downloaded yet.

    Only ever Fuwari's own copy. A pip-installed `unidic` is deliberately
    ignored: a half-removed one broke tokenizing, and one source is simpler.
    """
    return UNIDIC_DIR if _complete(UNIDIC_DIR) else None


def is_installed():
    return find_dicdir() is not None


def mecab_args():
    """Arguments for fugashi's Tagger, or None if UniDic is missing."""
    dicdir = find_dicdir()
    if dicdir is None:
        return None
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(_MECABRC):
        open(_MECABRC, 'w').close()
    return f'-r "{_MECABRC}" -d "{dicdir}"'


def _ssl_context():
    """Certificates to check the download with.

    The AppImage's Python comes from an old build base whose default
    certificate location usually does not exist on the user's system, so an
    https download fails with a certificate error. The system's own bundle is
    looked up instead.
    """
    paths = ssl.get_default_verify_paths()
    if ((paths.cafile and os.path.exists(paths.cafile))
            or (paths.capath and os.path.isdir(paths.capath))):
        return ssl.create_default_context()
    for cafile in ('/etc/ssl/certs/ca-certificates.crt',   # Arch, Debian, Ubuntu
                   '/etc/pki/tls/certs/ca-bundle.crt',     # Fedora, RHEL
                   '/etc/ssl/ca-bundle.pem',               # openSUSE
                   '/etc/ssl/cert.pem'):                   # Alpine, others
        if os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def download(progress=None):
    """Download and install UniDic into UNIDIC_DIR. Blocks; run it on a thread.

    progress(done_bytes, total_bytes) is called as the download goes, with
    total_bytes 0 if the server did not say. Raises on any failure, and never
    leaves a half-installed dictionary behind: the old one, if any, is only
    replaced once the new one is complete.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    shutil.rmtree(_WORK_DIR, ignore_errors=True)
    os.makedirs(_WORK_DIR)
    try:
        zip_path = os.path.join(_WORK_DIR, 'unidic.zip')
        req = urllib.request.Request(UNIDIC_URL, headers={'User-Agent': 'Fuwari'})
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=30) as resp, \
                open(zip_path, 'wb') as out:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if total and done != total:
            raise IOError(f"download stopped early ({done} of {total} bytes)")

        extract_dir = os.path.join(_WORK_DIR, 'extract')
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        # Free the space before moving anything, since the zip and its
        # contents together are well over a gigabyte.
        os.remove(zip_path)

        # Found by its contents rather than an assumed folder name, so a
        # repackaged zip still installs.
        found = None
        for root, _dirs, _files in os.walk(extract_dir):
            if _complete(root):
                found = root
                break
        if found is None:
            raise IOError("the download did not contain a MeCab dictionary")

        with open(os.path.join(found, 'VERSION'), 'w') as f:
            f.write(UNIDIC_VERSION + '\n')

        old = UNIDIC_DIR + '.old'
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(UNIDIC_DIR):
            os.replace(UNIDIC_DIR, old)
        os.replace(found, UNIDIC_DIR)
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(_WORK_DIR, ignore_errors=True)
