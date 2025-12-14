#!/usr/bin/env python3
# /opt/docker/webapp/app.py

import os
from flask import Flask, render_template, request, Response, stream_with_context, send_from_directory, url_for, redirect

from dotenv import load_dotenv
load_dotenv('.env.local', override=True)

# Import unified sync engine
from scripts import media_sync

# Media watcher
from scripts import auto_runner
import threading

from pathlib import Path

app = Flask(__name__, static_folder='static', template_folder='templates')

# CONFIG - edit if your paths differ
DEV_MODE = os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes')

if DEV_MODE:
    BASENAME_4K = os.path.expandvars(os.getenv('DEV_BASENAME_4K', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_4k'))
    BASENAME_1080 = os.path.expandvars(os.getenv('DEV_BASENAME_1080', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_1080'))
    MEDIA_SHOWS = os.path.expandvars(os.getenv('DEV_MEDIA_SHOWS', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\shows'))
    MEDIA_MOVIES = os.path.expandvars(os.getenv('DEV_MEDIA_MOVIES', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\movies'))
else:
    BASENAME_4K = "/mnt/debrid/riven_symlinks"
    BASENAME_1080 = "/mnt/debrid_1080/riven_symlinks"
    MEDIA_SHOWS = "/media/shows"
    MEDIA_MOVIES = "/media/movies"

threading.Thread(
    target=auto_runner.loop,
    daemon=True
).start()

###############################################################################
# Helpers
###############################################################################

def safe_listdir(path):
    try:
        return sorted([d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))])
    except Exception:
        return []

def list_shows():
    return safe_listdir(MEDIA_SHOWS)

def list_movies():
    return safe_listdir(MEDIA_MOVIES)

def list_movie(movie):
    # movie_dir = Path(MEDIA_MOVIES) / movie
    # if not movie_dir.exists():
    #     return []
    # return sorted(p.name for p in movie_dir.iterdir() if p.is_symlink())
    base = os.path.join(MEDIA_MOVIES, movie)
    movies = []
    try:
        for f in sorted(os.listdir(base)):
            p = os.path.join(base, f)
            if os.path.isfile(p) or os.path.islink(p):
                if f.lower().endswith((".mkv", ".mp4")):
                    movies.append(f)
    except FileNotFoundError:
        pass
    return movies

def list_seasons(show):
    base = os.path.join(MEDIA_SHOWS, show)
    try:
        return sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    except FileNotFoundError:
        return []

def list_episodes(show, season):
    base = os.path.join(MEDIA_SHOWS, show, season)
    episodes = []
    try:
        for f in sorted(os.listdir(base)):
            p = os.path.join(base, f)
            if os.path.isfile(p) or os.path.islink(p):
                if f.lower().endswith((".mkv", ".mp4")):
                    episodes.append(f)
    except FileNotFoundError:
        pass
    return episodes

def list_movie_files(movie):
    movie_dir = MEDIA_MOVIES / movie
    if not movie_dir.exists():
        return []
    return sorted(p.name for p in movie_dir.iterdir() if p.is_symlink())


###############################################################################
# Streaming wrapper — yields lines from Python generator
###############################################################################

def stream_python(generator_fn):
    def inner():
        for line in generator_fn():
            yield line + "\n"
    return Response(stream_with_context(inner()), mimetype='text/plain; charset=utf-8')

###############################################################################
# Routes
###############################################################################

@app.route('/')
def index():
    return render_template('index.html',
                           shows=list_shows(),
                           movies=list_movies())

@app.route('/show/<path:show>')
def show_page(show):
    return render_template('show.html',
                           show=show,
                           seasons=list_seasons(show),
                           list_episodes=list_episodes)

@app.route('/movie/<path:movie>')
def movie_page(movie):
    return render_template(
        'movie.html',
        movie=movie,
        files=list_movie(movie)
    )

###############################################################################
# Run refresh endpoints (NO subprocess — mounted directly to Python functions)
###############################################################################

@app.route('/run/refresh_show', methods=['POST'])
def refresh_show():
    show = request.form.get('show', '').strip()
    if not show:
        return "Missing show", 400

    def gen():
        yield f"=== Refreshing TV show: {show} (4K) ==="
        for line in media_sync.sync_tv_4k(show_filter=show, wipe_dest=True):
            yield line

        yield ""
        yield f"=== Refreshing TV show: {show} (1080p) ==="
        for line in media_sync.sync_tv_1080(show_filter=show):
            yield line

    return stream_python(gen)

@app.route('/run/refresh_movie', methods=['POST'])
def refresh_movie():
    movie = request.form.get('movie', '').strip()
    if not movie:
        return "Missing movie", 400

    def gen():
        yield f"=== Refreshing movie: {movie} (4K) ==="
        for line in media_sync.sync_movies_4k(movie_filter=movie, wipe_dest=True):
            yield line

        yield ""
        yield f"=== Refreshing movie: {movie} (1080p) ==="
        for line in media_sync.sync_movies_1080(movie_filter=movie):
            yield line

    return stream_python(gen)


@app.route('/run/refresh_all', methods=['POST'])
def refresh_all():
    def gen():
        yield "=== Full refresh: ALL media ==="
        for line in media_sync.sync_all(full=True):
            yield line

    return stream_python(gen)

@app.route('/run/refresh_movies_inc', methods=['POST'])
def refresh_movies_inc():
    def gen():
        yield "=== Incremental Movies 4K ==="
        for line in media_sync.sync_movies_4k():
            yield line

        yield ""
        yield "=== Incremental Movies 1080p ==="
        for line in media_sync.sync_movies_1080():
            yield line

    return stream_python(gen)

@app.route('/run/refresh_shows_inc', methods=['POST'])
def refresh_shows_inc():
    def gen():
        yield "=== Incremental TV 4K ==="
        for line in media_sync.sync_tv_4k():
            yield line

        yield ""
        yield "=== Incremental TV 1080p ==="
        for line in media_sync.sync_tv_1080():
            yield line

    return stream_python(gen)

###############################################################################
# Misc
###############################################################################

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)

@app.route('/ui')
def ui():
    return redirect(url_for('index'))

###############################################################################
# Media watcher endpoints
###############################################################################
# @app.route("/watcher/start", methods=["POST"])
# def start_watcher_route():
#     media_watcher.start_watcher()
#     return "Watcher started\n"

# @app.route("/watcher/stop", methods=["POST"])
# def stop_watcher_route():
#     media_watcher.stop()
#     return "Watcher stopping\n"

###############################################################################

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8095, debug=False)
