# config.py
from pathlib import Path
import os
import time

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
SRC_MOVIES_4K   = Path("/mnt/debrid/riven_symlinks/movies")
SRC_MOVIES_1080 = Path("/mnt/debrid_1080/riven_symlinks/movies")

SRC_TV_4K       = Path("/mnt/debrid/riven_symlinks/shows")
SRC_TV_1080     = Path("/mnt/debrid_1080/riven_symlinks/shows")


# -----------------------------------------------------------
# Destination paths
# -----------------------------------------------------------
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
