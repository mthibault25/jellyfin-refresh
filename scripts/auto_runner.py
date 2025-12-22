import time
import signal
from scripts import media_sync

from config import (
    AUTO_RUNNING,
    SLEEP_SECONDS,
)

RUNNING = AUTO_RUNNING
SLEEP_SECONDS = SLEEP_SECONDS

def shutdown(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

def drain(gen):
    """Fully consume a sync generator"""
    for _ in gen:
        pass

def loop():
    while RUNNING:
        try:
            # TV
            # drain(media_sync.sync_tv())

            # Movies
            # drain(media_sync.sync_movies())
            drain(media_sync.sync_all())

        except Exception:
            # media_sync already logs
            pass

        time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    loop()
