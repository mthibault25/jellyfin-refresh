import time
import hashlib
from pathlib import Path
import threading

from scripts import media_sync

WATCH_PATHS = {
    "tv_4k": Path("/mnt/debrid/riven_symlinks/tv_4k"),
    "tv_1080": Path("/mnt/debrid_1080/riven_symlinks/tv"),
    "movies_4k": Path("/mnt/debrid/riven_symlinks/movies"),
    "movies_1080": Path("/mnt/debrid_1080/riven_symlinks/movies"),
}

POLL_INTERVAL = 15

_stop_event = threading.Event()

def stop():
    _stop_event.set()

def fingerprint(path: Path) -> str:
    h = hashlib.sha1()
    for p in sorted(path.rglob("*")):
        try:
            h.update(p.name.encode())
            h.update(str(p.stat().st_mtime_ns).encode())
        except FileNotFoundError:
            continue
    return h.hexdigest()

def watcher_loop():
    last_fp = {}

    while not _stop_event.is_set():
        for key, path in WATCH_PATHS.items():
            if not path.exists():
                continue

            fp = fingerprint(path)
            if last_fp.get(key) != fp:
                last_fp[key] = fp

                if key == "tv_4k":
                    media_sync.sync_tv_4k()
                elif key == "tv_1080":
                    media_sync.sync_tv_1080()
                elif key == "movies_4k":
                    media_sync.sync_movies_4k()
                elif key == "movies_1080":
                    media_sync.sync_movies_1080()

        _stop_event.wait(POLL_INTERVAL)
