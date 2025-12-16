# config.py
from pathlib import Path
import os
import time

from dotenv import load_dotenv
load_dotenv('.env.local', override=True)

DEV_MODE = os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes')


# -----------------------------------------------------------
# Timezone
# -----------------------------------------------------------
TZ = "America/Toronto"

os.environ.setdefault("TZ", TZ)
try:
    time.tzset()
except Exception:
    pass


# -----------------------------------------------------------
# Base directories
# -----------------------------------------------------------
DATA_DIR = Path("/data")

CACHE_DIR = DATA_DIR / "cache"
LOG_DIR   = DATA_DIR / "logs"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------
# Log file names
# -----------------------------------------------------------
LOG_TV_4K     = "tv-4k.log"
LOG_TV_1080   = "tv-1080.log"
LOG_MOVIE_4K  = "movie-4k.log"
LOG_MOVIE_1080= "movie-1080.log"


# -----------------------------------------------------------
# Source paths
# -----------------------------------------------------------
if DEV_MODE:
    SRC_MOVIES_4K = os.path.expandvars(os.getenv('DEV_BASENAME_4K', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid\\movies'))
    SRC_MOVIES_1080 = os.path.expandvars(os.getenv('DEV_BASENAME_1080', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_1080\\movies'))
    SRC_TV_4K = os.path.expandvars(os.getenv('DEV_BASENAME_4K', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid\\shows'))
    SRC_TV_1080 = os.path.expandvars(os.getenv('DEV_BASENAME_1080', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_1080\\shows'))
else:
    SRC_MOVIES_4K   = Path("/mnt/debrid/riven_symlinks/movies")
    SRC_MOVIES_1080 = Path("/mnt/debrid_1080/riven_symlinks/movies")

    SRC_TV_4K       = Path("/mnt/debrid/riven_symlinks/shows")
    SRC_TV_1080     = Path("/mnt/debrid_1080/riven_symlinks/shows")

# -----------------------------------------------------------
# Destination paths
# -----------------------------------------------------------
if DEV_MODE:
    DEST_TV = os.path.expandvars(os.getenv('DEV_DEST_TV', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\shows'))
    DEST_MOVIES = os.path.expandvars(os.getenv('DEV_DEST_MOVIES', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\movies'))
else:
    DEST_MOVIES = Path("/media/movies")
    DEST_TV     = Path("/media/shows")


# -----------------------------------------------------------
# Cache files
# -----------------------------------------------------------
CACHE_FILES = {
    "movies_4k":   CACHE_DIR / "movies-4k.last",
    "movies_1080": CACHE_DIR / "movies-1080.last",
    "tv_4k":       CACHE_DIR / "tv-4k.last",
    "tv_1080":     CACHE_DIR / "tv-1080.last",
}


# -----------------------------------------------------------
# Default resolutions
# -----------------------------------------------------------
DEFAULT_RES = {
    "4k": "2160p",
    "1080": "1080p",
}


# -----------------------------------------------------------
# Sync parameters
# -----------------------------------------------------------
AUTO_RUNNING=True
SLEEP_SECONDS=30
