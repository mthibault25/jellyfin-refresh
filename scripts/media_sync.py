#!/usr/bin/env python3
"""
media_sync.py

Unified TV + Movies symlink-to-jellyfin sync module.

Public functions you can import & call:
  - sync_movies_4k(full=False, movie_filter=None)
  - sync_movies_1080(full=False, movie_filter=None)
  - sync_tv_4k(full=False, show_filter=None, episode_filter=None)
  - sync_tv_1080(full=False, show_filter=None, episode_filter=None)
  - sync_movie(movie_name)            # convenience: picks best resolution by checking paths
  - sync_show(show_name)              # convenience
  - sync_episode(show_name, ep_code)  # convenience (e.g. "S01E03")
  - sync_all()                        # runs 4K then 1080 for movies and tv

Also supports CLI usage when run directly:
  ./media_sync.py --mode movies --res 4k --full
  ./media_sync.py --mode tv --res 1080 --show "My Show" --episode S01E01

Logging:
  /opt/docker/logs/tv_4k.log
  /opt/docker/logs/tv_1080.log
  /opt/docker/logs/movie_4k.log
  /opt/docker/logs/movie_1080.log
"""
from __future__ import annotations
import os
import sys
import time
import subprocess
import logging
from pathlib import Path
import stat
import re
import argparse
from typing import List, Tuple, Optional, Callable
import shutil

# -----------------------------------------------------------
# ENV / DEFAULT PATHS (confirmed)
# -----------------------------------------------------------
os.environ.setdefault("TZ", "America/Toronto")
try:
    time.tzset()
except Exception:
    # windows may not support tzset; that's fine
    pass

CACHE_DIR = Path("/opt/riven-cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = Path("/opt/docker/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_TV_4k= "tv-4k.log"
LOG_TV_1080= "tv-1080.log"
LOG_MOVIE_4k= "movie-4k.log"
LOG_MOVIE_1080= "movie-1080.log"

# Source paths (per your confirmation)
SRC_MOVIES_4K = Path("/mnt/debrid/riven_symlinks/movies")
SRC_MOVIES_1080 = Path("/mnt/debrid_1080/riven_symlinks/movies")
DEST_MOVIES = Path("/media/movies")

SRC_TV_4K = Path("/mnt/debrid/riven_symlinks/shows")
SRC_TV_1080 = Path("/mnt/debrid_1080/riven_symlinks/shows")
DEST_TV = Path("/media/shows")


# -----------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------
def _make_logger(name: str, log_path: Path) -> logging.Logger:
    """
    Create (or return) a logger that writes to log_path and stdout.
    The format is kept minimal to match your existing scripts.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.INFO)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(message)s")

    fh = logging.FileHandler(log_path, mode="a")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # don't propagate to root
    logger.propagate = False
    return logger


# -----------------------------------------------------------
# Resolution detection helpers (shared)
# -----------------------------------------------------------
def _detect_filename_res(name: str) -> Optional[str]:
    n = name.lower()
    if "2160" in n or "4k" in n or "uhd" in n:
        return "2160p"
    if "1080" in n:
        return "1080p"
    return None


def _detect_keyword_res(name: str) -> Optional[str]:
    n = name.lower()
    # dv vs dovi matching; hdr; avc
    if "dv" in n or "dovi" in n or "hdr" in n:
        return "2160p"
    if "avc" in n:
        return "1080p"
    return None


def _detect_folder_res(name: str) -> Optional[str]:
    n = name.lower()
    if "2160" in n or "4k" in n:
        return "2160p"
    if "1080" in n:
        return "1080p"
    return None


def _probe_resolution(path: str) -> Optional[str]:
    """
    Uses ffprobe to determine video width, maps to 2160p/1080p/720p.
    Non-fatal: returns None on failure.
    """
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", path],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode().strip()
        if not out:
            return None
        w = int(out)
        if w >= 3800:
            return "2160p"
        if w >= 1900:
            return "1080p"
        return "720p"
    except Exception:
        return None


def detect_resolution(target_path: str, default_res: str) -> str:
    """
    Try filename -> keywords -> parent folder -> ffprobe -> default.
    """
    base = os.path.basename(target_path)
    r = _detect_filename_res(base)
    if r:
        return r
    r = _detect_keyword_res(base)
    if r:
        return r
    parent = os.path.basename(os.path.dirname(target_path))
    r = _detect_folder_res(parent)
    if r:
        return r
    r = _probe_resolution(target_path)
    if r:
        return r
    return default_res


# -----------------------------------------------------------
# Generic filesystem helpers
# -----------------------------------------------------------
def find_symlinks_sorted(src: Path) -> List[Tuple[float, str]]:
    """
    Walk src and return list of tuples (mtime, path) for symlink files,
    sorted newest -> oldest.
    """
    records: List[Tuple[float, str]] = []
    if not src.exists():
        return records

    for root, _, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.lstat(p)
                if stat.S_ISLNK(st.st_mode):
                    records.append((st.st_mtime, p))
            except Exception:
                continue
    records.sort(key=lambda x: x[0], reverse=True)
    return records


def atomic_symlink(target: Path, dest: Path) -> None:
    """
    Create symlink dest -> target atomically using a tmp file.
    """
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        if tmp.exists():
            tmp.unlink()
        os.symlink(str(target), str(tmp))
        os.replace(str(tmp), str(dest))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

def wipe_dest_folder(path: Path, logger):
    if not path.exists():
        return
    logger.info(f"Removing destination folder: {path}")
    try:
        shutil.rmtree(path)
    except Exception as e:
        logger.info(f"Failed to remove {path}: {e}")

def _sync_engine(
    *,
    src: Path,
    dest_root: Path,
    cache_last_file: Path,
    default_res: str,
    log_path: Path,
    is_tv: bool,
    full: bool = False,
    filter_show: Optional[str] = None,
    filter_episode: Optional[str] = None,
    filter_movie: Optional[str] = None,
    wipe_dest: bool = False,
):

    """
    Core sync routine. Yields log lines for UI streaming.
    Never returns booleans.
    """
    logger = _make_logger(log_path.stem, log_path)

    def out(msg: str):
        logger.info(msg)
        yield msg + "\n"

    # header
    now_human = time.strftime("%Y-%m-%d %H:%M:%S")
    kind = "TV" if is_tv else "MOVIE"

    yield from out("")
    yield from out(f"================ {kind} SYNC: {now_human} ================")
    yield from out("")

    # destructive refresh for targeted runs
    if wipe_dest:
        if is_tv and filter_show:
            dest_show = dest_root / filter_show
            yield from out(f"Removing destination folder: {dest_show}")
            wipe_dest_folder(dest_show, logger)

        if not is_tv and filter_movie:
            dest_movie = dest_root / filter_movie
            yield from out(f"Removing destination folder: {dest_movie}")
            wipe_dest_folder(dest_movie, logger)



    # ensure last file exists
    cache_last_file.parent.mkdir(parents=True, exist_ok=True)
    cache_last_file.touch(exist_ok=True)

    update_last_file = True

    if full or filter_show or filter_episode or filter_movie:
        prev_ts = 0
        update_last_file = False
    else:
        try:
            prev_ts = int(cache_last_file.read_text().strip() or "0")
        except Exception:
            prev_ts = 0

    now_ts = int(time.time())

    yield from out(f"{kind} SYNC:")
    yield from out(f" SRC          = {src}")
    yield from out(f" PREV_TS      = {prev_ts}")
    yield from out(f" FULL MODE    = {full}")

    if is_tv:
        yield from out(f" FILTER_SHOW  = '{filter_show}'")
        yield from out(f" FILTER_EP    = '{filter_episode}'")
    else:
        yield from out(f" FILTER_MOVIE = '{filter_movie}'")

    yield from out("")

    processed_any = False
    symlinks = find_symlinks_sorted(src)

    for ts, link in symlinks:

        # movie filter
        if filter_movie and not is_tv:
            movie_name = Path(link).parent.name
            if movie_name != filter_movie:
                continue

        # show filter
        if filter_show and is_tv:
            try:
                show_name = Path(link).parent.parent.name
            except Exception:
                show_name = ""
            if show_name != filter_show:
                continue

        # stop early
        if update_last_file and ts <= prev_ts:
            yield from out("Stopping early: symlink <= last-run")
            break

        try:
            link_path = Path(link)
            basename = link_path.name

            # resolve target
            try:
                target = link_path.resolve(strict=True)
            except FileNotFoundError:
                yield from out(f"Broken symlink: {link}")
                continue

            # tv seasons
            if is_tv:
                show_dir = link_path.parent.parent.name
                season_dir = link_path.parent.name
            else:
                movie_name = link_path.parent.name

            # ep filter
            if is_tv and filter_episode:
                m = re.search(r"([Ss]\d{2}[Ee]\d{2})", basename)
                ep = m.group(1) if m else ""
                if ep != filter_episode:
                    continue

            yield from out(f"NEW: {link}")

            # resolution detection
            res = detect_resolution(str(target), default_res)

            if res not in basename:
                name, ext = os.path.splitext(basename)
                new_name = f"{name} - {res}{ext}"
                new_link = link_path.parent / new_name

                try:
                    link_path.rename(new_link)
                    yield from out(f" RENAMED: {new_name}")
                    link_path = new_link
                    basename = new_name
                    processed_any = True
                except Exception as e:
                    yield from out(f" Rename failed {link} -> {new_name}: {e}")

            # dest path
            if is_tv:
                dest_path = dest_root / show_dir / season_dir / basename
            else:
                dest_path = dest_root / movie_name / basename

            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if dest_path.exists() or dest_path.is_symlink():
                yield from out(f" Already linked: {dest_path}")
                continue

            try:
                atomic_symlink(target, dest_path)
                yield from out(f" Linked: {dest_path}")
                processed_any = True
            except Exception as e:
                yield from out(f" Link failed: {dest_path}: {e}")
                continue

        except Exception as exc:
            yield from out(f"Error processing {link}: {exc}")
            continue

    # timestamps
    if update_last_file and processed_any:
        try:
            cache_last_file.write_text(str(now_ts))
            human = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
            yield from out(f"Updated timestamp: {human} ({now_ts})")
        except Exception as e:
            yield from out(f"Failed to update timestamp file {cache_last_file}: {e}")

    elif update_last_file and not processed_any:
        yield from out("No changes detected; timestamp not updated.")

    else:
        yield from out("Skipped timestamp update (targeted or full refresh).")

    yield from out(f"{kind} SYNC COMPLETE\n")



# -----------------------------------------------------------
# Public convenience wrappers
# -----------------------------------------------------------
def sync_movies_4k(full=False, movie_filter=None, wipe_dest=False):
    return _sync_engine(
        src=SRC_MOVIES_4K,
        dest_root=DEST_MOVIES,
        cache_last_file=CACHE_DIR / "movies-4k.last",
        default_res="2160p",
        log_path=LOG_DIR / LOG_MOVIE_4k,
        is_tv=False,
        full=full,
        filter_movie=movie_filter,
        wipe_dest=wipe_dest,
    )


def sync_movies_1080(full=False, movie_filter=None):
    return _sync_engine(
        src=SRC_MOVIES_1080,
        dest_root=DEST_MOVIES,
        cache_last_file=CACHE_DIR / "movies-1080.last",
        default_res="1080p",
        log_path=LOG_DIR / LOG_MOVIE_1080,
        is_tv=False,
        full=full,
        filter_movie=movie_filter,
        wipe_dest=False,  # 👈 NEVER wipe here
    )



def sync_tv_4k(full: bool = False, show_filter: Optional[str] = None, episode_filter: Optional[str] = None) -> bool:
    return _sync_engine(
        src=SRC_TV_4K,
        dest_root=DEST_TV,
        cache_last_file=CACHE_DIR / "tv-4k.last",
        default_res="2160p",
        log_path=LOG_DIR / LOG_TV_4k,
        is_tv=True,
        full=full,
        filter_show=show_filter,
        filter_episode=episode_filter,
    )


def sync_tv_1080(full: bool = False, show_filter: Optional[str] = None, episode_filter: Optional[str] = None) -> bool:
    return _sync_engine(
        src=SRC_TV_1080,
        dest_root=DEST_TV,
        cache_last_file=CACHE_DIR / "tv-1080.last",
        default_res="1080p",
        log_path=LOG_DIR / LOG_TV_1080,
        is_tv=True,
        full=full,
        filter_show=show_filter,
        filter_episode=episode_filter,
    )


def sync_movie(movie_name: str) -> None:
    """
    Convenience: attempt 4k then 1080 for the named movie.
    """
    # try 4k first
    if SRC_MOVIES_4K.exists():
        sync_movies_4k(full=False, movie_filter=movie_name)
    if SRC_MOVIES_1080.exists():
        sync_movies_1080(full=False, movie_filter=movie_name)


def sync_show(show_name: str) -> None:
    """
    Convenience: attempt 4k then 1080 for the named show.
    """
    if SRC_TV_4K.exists():
        sync_tv_4k(full=False, show_filter=show_name)
    if SRC_TV_1080.exists():
        sync_tv_1080(full=False, show_filter=show_name)


def sync_episode(show_name: str, episode_code: str) -> None:
    """
    Convenience: sync a specific episode for a show (tries 4k then 1080).
    episode_code should look like 'S01E03'.
    """
    if SRC_TV_4K.exists():
        sync_tv_4k(full=False, show_filter=show_name, episode_filter=episode_code)
    if SRC_TV_1080.exists():
        sync_tv_1080(full=False, show_filter=show_name, episode_filter=episode_code)


def sync_all() -> None:
    """
    Run all four syncs in this order: movies 4k, movies 1080, tv 4k, tv 1080.
    """
    sync_movies_4k()
    sync_movies_1080()
    sync_tv_4k()
    sync_tv_1080()


# -----------------------------------------------------------
# CLI support for ad-hoc running
# -----------------------------------------------------------
def _cli():
    p = argparse.ArgumentParser(description="media_sync - unified tv & movies sync")
    p.add_argument("--mode", choices=["movies", "tv", "all"], default="all", help="Which content to sync")
    p.add_argument("--res", choices=["4k", "1080", "both"], default="both", help="Resolution to target")
    p.add_argument("--full", action="store_true", help="Full run (do not update timestamp file)")
    p.add_argument("--movie", help="Filter a specific movie name (movies mode)")
    p.add_argument("--show", help="Filter a specific show name (tv mode)")
    p.add_argument("--episode", help="Filter a specific episode code, e.g. S01E03 (tv mode)")
    p.add_argument("--src", help="Optional custom src path (overrides built-ins)")

    args = p.parse_args()

    # small helper to override src if provided
    if args.mode in ("movies", "all"):
        if args.res in ("4k", "both"):
            if args.src:
                # call engine directly with custom src
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_MOVIES,
                    cache_last_file=CACHE_DIR / "movies-4k.last",
                    default_res="2160p",
                    log_path=LOG_DIR / LOG_MOVIE_4k,
                    is_tv=False,
                    full=args.full,
                    filter_movie=args.movie,
                )
            else:
                sync_movies_4k(full=args.full, movie_filter=args.movie)
        if args.res in ("1080", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_MOVIES,
                    cache_last_file=CACHE_DIR / "movies-1080.last",
                    default_res="1080p",
                    log_path=LOG_DIR / LOG_MOVIE_1080,
                    is_tv=False,
                    full=args.full,
                    filter_movie=args.movie,
                )
            else:
                sync_movies_1080(full=args.full, movie_filter=args.movie)

    if args.mode in ("tv", "all"):
        if args.res in ("4k", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_TV,
                    cache_last_file=CACHE_DIR / "tv-4k.last",
                    default_res="2160p",
                    log_path=LOG_DIR / LOG_TV_4k,
                    is_tv=True,
                    full=args.full,
                    filter_show=args.show,
                    filter_episode=args.episode,
                )
            else:
                sync_tv_4k(full=args.full, show_filter=args.show, episode_filter=args.episode)
        if args.res in ("1080", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_TV,
                    cache_last_file=CACHE_DIR / "tv-1080.last",
                    default_res="1080p",
                    log_path=LOG_DIR / LOG_TV_1080,
                    is_tv=True,
                    full=args.full,
                    filter_show=args.show,
                    filter_episode=args.episode,
                )
            else:
                sync_tv_1080(full=args.full, show_filter=args.show, episode_filter=args.episode)


if __name__ == "__main__":
    _cli()
