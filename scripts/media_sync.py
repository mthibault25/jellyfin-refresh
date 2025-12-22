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
"""

from __future__ import annotations
import os
import time
import subprocess
import logging
from pathlib import Path
import stat
import re
import argparse
from typing import List, Tuple, Optional
import shutil

# -----------------------------------------------------------
# ENV / DEFAULT PATHS (confirmed)
# -----------------------------------------------------------
from config import (
    LOG_DIR,
    LOG_FILE,
    DEST_MOVIES,
    DEST_TV,
    CACHE_FILES,
    DEFAULT_RES,
    MediaSource,
    MOVIE_SOURCES,
    TV_SOURCES,
)

from scripts import jellyfin_scan as scanner

# -----------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------
def _make_logger(name: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 🔥 ALWAYS reset handlers so format changes take effect
    logger.handlers.clear()

    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger



# -----------------------------------------------------------
# Resolution detection helpers (shared)
# -----------------------------------------------------------
def _detect_filename_res(name: str) -> Optional[str]:
    n = name.lower()
    if "2160" in n or "4k" in n or "uhd" in n:
        return DEFAULT_RES["4k"]
    if "1080" in n:
        return DEFAULT_RES["1080"]
    return None


def _detect_keyword_res(name: str) -> Optional[str]:
    n = name.lower()
    # dv vs dovi matching; hdr; avc
    if "dv" in n or "dovi" in n or "hdr" in n:
        return DEFAULT_RES["4k"]
    if "avc" in n:
        return DEFAULT_RES["1080"]
    return None


def _detect_folder_res(name: str) -> Optional[str]:
    n = name.lower()
    if "2160" in n or "4k" in n:
        return DEFAULT_RES["4k"]
    if "1080" in n:
        return DEFAULT_RES["1080"]
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
            return DEFAULT_RES["4k"]
        if w >= 1900:
            return DEFAULT_RES["1080"]
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

def wipe_dest_folder(path: Path):
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except Exception as e:
        raise RuntimeError(f"Failed to wipe destination folder {path}: {e}")

def already_tagged(name: str) -> bool:
    return bool(re.search(r"\s-\s(2160p|1080p|720p)", name))

# -----------------------------------------------------------
# Core sync engine  (reusable)
# -----------------------------------------------------------
def sync_sources(
    sources: list[MediaSource],
    *,
    dest_root: Path,
    is_tv: bool,
    full: bool = False,
    movie_filter: str | None = None,
    show_filter: str | None = None,
    episode_filter: str | None = None,
    wipe_dest: bool = False,
):

    any_updates = False

    dest_root = Path(dest_root)

    # 🔥 WIPE ONCE PER RUN
    if wipe_dest:
        if is_tv and show_filter:
            dest_path = dest_root / show_filter
        elif not is_tv and movie_filter:
            dest_path = dest_root / movie_filter
        else:
            dest_path = None

        if dest_path and dest_path.exists():
            wipe_dest_folder(dest_path)

    # 🔁 PROCESS SOURCES
    for source in sources:
        if not source.src.exists():
            continue

        updated = yield from _sync_engine(
            src=source.src,
            dest_root=dest_root,
            cache_last_file=source.cache_file,
            default_res=source.default_res,
            is_tv=is_tv,
            full=full,
            filter_movie=movie_filter,
            filter_show=show_filter,
            filter_episode=episode_filter,
        )

        if updated:
            any_updates = True

    return any_updates



def _sync_engine(
    *,
    src: Path,
    dest_root: Path,
    cache_last_file: Path,
    default_res: str,
    is_tv: bool,
    full: bool = False,
    filter_show: Optional[str] = None,
    filter_episode: Optional[str] = None,
    filter_movie: Optional[str] = None,
):
    src = Path(src)
    dest_root = Path(dest_root)
    cache_last_file = Path(cache_last_file)
    log_path = Path(LOG_DIR / LOG_FILE)

    """
    Core sync routine. Yields log lines for UI streaming.
    Never returns booleans.
    """
    logger = _make_logger(log_path.stem, log_path)

    def out(msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(msg)
        yield f"[{ts}] {msg}\n"

    # header
    # now_human = time.strftime("%Y-%m-%d %H:%M:%S")
    # kind = "TV" if is_tv else "MOVIE"

    # yield from out("")
    # yield from out(f"================ {kind} SYNC: {now_human} ================")
    # yield from out("")

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

    # yield from out(f"{kind} SYNC:")
    # yield from out(f" SRC          = {src}")
    # yield from out(f" PREV_TS      = {prev_ts}")
    # yield from out(f" FULL MODE    = {full}")

    # if is_tv:
    #     yield from out(f" FILTER_SHOW  = '{filter_show}'")
    #     yield from out(f" FILTER_EP    = '{filter_episode}'")
    # else:
    #     yield from out(f" FILTER_MOVIE = '{filter_movie}'")

    # yield from out("")

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
            # yield from out("Stopping early: symlink <= last-run")
            break

        try:
            link_path = Path(link)
            basename = link_path.name

            # resolve target
            if not link_path.is_symlink():
                yield from out(f"Not a symlink: {link}")
                continue

            try:
                target = Path(os.readlink(link_path))
            except OSError as e:
                yield from out(f"Unresolvable symlink target (expected for RD): {link}")
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

            # rename only if file has NEVER been tagged
            if not already_tagged(basename):
                res = detect_resolution(str(target), default_res)

                name, ext = os.path.splitext(basename)
                new_name = f"{name} - {res}{ext}"
                new_link = link_path.parent / new_name

                try:
                    link_path.rename(new_link)
                    yield from out(f" RENAMED: {new_name}")
                    link_path = new_link
                    basename = new_name
                    processed_any = True
                except FileNotFoundError:
                    # stale snapshot — safe to ignore
                    continue


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
            # yield from out(f"Timestamp updated")
            scanner.trigger_scan()
        except Exception as e:
            yield from out(f"Failed to update timestamp file {cache_last_file}: {e}")

    elif update_last_file and not processed_any:
        pass
    #     yield from out("No changes detected; timestamp not updated.")

    # else:
    #     yield from out("Skipped timestamp update (targeted or full refresh).")

    # yield from out(f"{kind} SYNC COMPLETE\n")
    return processed_any


# -----------------------------------------------------------
# Public convenience wrappers
# -----------------------------------------------------------
def sync_movies(full=False, movie_filter=None, wipe_dest=False):
    movies_processed = yield from sync_sources(
        MOVIE_SOURCES,
        dest_root=DEST_MOVIES,
        is_tv=False,
        full=full,
        movie_filter=movie_filter,
        wipe_dest=wipe_dest,
    )
    return movies_processed

def sync_tv(full=False, show_filter=None, episode_filter=None, wipe_dest=False):
    tv_processed = yield from sync_sources(
        TV_SOURCES,
        dest_root=DEST_TV,
        is_tv=True,
        full=full,
        show_filter=show_filter,
        episode_filter=episode_filter,
        wipe_dest=wipe_dest,
    )
    return tv_processed

def sync_movie(movie_name: str):
    movies_processed = yield from sync_movies(full=False, movie_filter=movie_name)
    final_log(movies_processed=movies_processed)

def sync_show(show_name: str):
    tv_processed =  yield from sync_tv(full=False, show_filter=show_name)
    final_log(tv_processed=tv_processed)

def sync_episode(show_name: str, episode_code: str):
    tv_processed = yield from sync_tv(full=False, show_filter=show_name, episode_filter=episode_code)
    final_log(tv_processed=tv_processed)

def sync_all():
    movies_processed = yield from sync_movies()
    tv_processed = yield from sync_tv()
    yield f'tv_processed={tv_processed}, movies_processed={movies_processed}'
    final_log(tv_processed=tv_processed, movies_processed=movies_processed)

def final_log(tv_processed: bool = None, movies_processed: bool = None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    
    if (tv_processed is None) and (movies_processed is None):
        return
    elif ((tv_processed is None) and (not movies_processed)) or ((movies_processed is None) and (not tv_processed)):
         yield f"[{ts}] No updates found across all sources.\n"
    elif not (movies_processed and tv_processed):        
        yield f"[{ts}] No updates found across all libraries.\n"

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
                    cache_last_file=CACHE_FILES["movies_4k"],
                    default_res=DEFAULT_RES["4k"],
                    log_path=LOG_DIR / LOG_MOVIE_4K,
                    is_tv=False,
                    full=args.full,
                    filter_movie=args.movie,
                )
            else:
                sync_movies(full=False, movie_filter=args.movie)
        if args.res in ("1080", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_MOVIES,
                    cache_last_file=CACHE_FILES["movies_1080"],
                    default_res=DEFAULT_RES["1080"],
                    log_path=LOG_DIR / LOG_MOVIE_1080,
                    is_tv=False,
                    full=args.full,
                    filter_movie=args.movie,
                )
            else:
                sync_movies(full=False, movie_filter=args.movie)

    if args.mode in ("tv", "all"):
        if args.res in ("4k", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_TV,
                    cache_last_file=CACHE_FILES["tv_4k"],
                    default_res=DEFAULT_RES["4k"],
                    log_path=LOG_DIR / LOG_TV_4K,
                    is_tv=True,
                    full=args.full,
                    filter_show=args.show,
                    filter_episode=args.episode,
                )
            else:
                sync_tv(full=False, show_filter=args.show, episode_filter=args.episode)

        if args.res in ("1080", "both"):
            if args.src:
                _sync_engine(
                    src=Path(args.src),
                    dest_root=DEST_TV,
                    cache_last_file=CACHE_FILES["tv_1080"],
                    default_res=DEFAULT_RES["1080"],
                    log_path=LOG_DIR / LOG_TV_1080,
                    is_tv=True,
                    full=args.full,
                    filter_show=args.show,
                    filter_episode=args.episode,
                )
            else:
                sync_tv(full=False, show_filter=args.show, episode_filter=args.episode)


if __name__ == "__main__":
    _cli()
