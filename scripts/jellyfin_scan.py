import time
import requests
import logging

from config import JELLYFIN_URL, API_KEY

def trigger_scan(logger: logging.Logger):
    url = f"{JELLYFIN_URL}/Library/Refresh"
    headers = {
        "X-Emby-Token": API_KEY
    }

    def out(msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(msg)
        yield f"[{ts}] {msg}\n"

    response = requests.post(url, headers=headers, timeout=10)
    response.raise_for_status()
    yield from out("Jellyfin library scan triggered")

if __name__ == "__main__":
    trigger_scan()
