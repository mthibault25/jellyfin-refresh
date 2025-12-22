import requests

from config import JELLYFIN_URL, API_KEY

def trigger_scan():
    url = f"{JELLYFIN_URL}/Library/Refresh"
    headers = {
        "X-Emby-Token": API_KEY
    }

    response = requests.post(url, headers=headers, timeout=10)
    response.raise_for_status()
    print("Jellyfin library scan triggered")

if __name__ == "__main__":
    trigger_scan()
