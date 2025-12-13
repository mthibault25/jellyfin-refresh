import time
import signal
import threading
from scripts import media_sync

RUNNING = True
SLEEP_SECONDS = 30

def shutdown(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

def loop():
    while RUNNING:
        try:
            # TV first
            media_sync.sync_tv_4k()
            media_sync.sync_tv_1080()

            # Movies
            media_sync.sync_movies_4k()
            media_sync.sync_movies_1080()

        except Exception:
            # media_sync already logs exceptions
            pass

        time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    loop()
