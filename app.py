#!/usr/bin/env python3
# /opt/docker/webapp/app.py
import os
import shlex
from flask import Flask, render_template, request, Response, stream_with_context, send_from_directory, url_for, redirect

import subprocess

# Load environment variables from .env.local if it exists (for local development)
from dotenv import load_dotenv
load_dotenv('.env.local', override=True)

app = Flask(__name__, static_folder='static', template_folder='templates')

# CONFIG - edit if your paths differ
# Use DEV_MODE environment variable to switch between local testing and remote production
DEV_MODE = os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes')

if DEV_MODE:
    # Local development paths (Windows-friendly)
    BASENAME_4K = os.path.expandvars(os.getenv('DEV_BASENAME_4K', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_4k'))
    BASENAME_1080 = os.path.expandvars(os.getenv('DEV_BASENAME_1080', '%LOCALAPPDATA%\\jellyfin-refresh-test\\debrid_1080'))
    MEDIA_SHOWS = os.path.expandvars(os.getenv('DEV_MEDIA_SHOWS', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\shows'))
    MEDIA_MOVIES = os.path.expandvars(os.getenv('DEV_MEDIA_MOVIES', '%LOCALAPPDATA%\\jellyfin-refresh-test\\media\\movies'))
    SHOWS_SCRIPT = os.path.expandvars(os.getenv('DEV_SHOWS_SCRIPT', '%LOCALAPPDATA%\\jellyfin-refresh-test\\scripts\\mock_sync.bat'))
    MOVIES_SCRIPT = os.path.expandvars(os.getenv('DEV_MOVIES_SCRIPT', '%LOCALAPPDATA%\\jellyfin-refresh-test\\scripts\\mock_sync.bat'))
else:
    # Remote production paths
    BASENAME_4K = "/mnt/debrid/riven_symlinks"
    BASENAME_1080 = "/mnt/debrid_1080/riven_symlinks"
    MEDIA_SHOWS = "/media/shows"
    MEDIA_MOVIES = "/media/movies"
    SHOWS_SCRIPT = "/opt/docker/scripts/sync_tv_folders.sh"
    MOVIES_SCRIPT = "/opt/docker/scripts/sync_movies_folders.sh"

# Utility helpers
def safe_listdir(path):
    try:
        return sorted([d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))])
    except FileNotFoundError:
        return []

def list_shows():
    return safe_listdir(MEDIA_SHOWS)

def list_movies():
    return safe_listdir(MEDIA_MOVIES)

def list_seasons(show):
    base = os.path.join(MEDIA_SHOWS, show)
    try:
        return sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))], key=lambda s: s)
    except FileNotFoundError:
        return []

def list_episodes(show, season):
    base = os.path.join(MEDIA_SHOWS, show, season)
    eps = []
    try:
        for f in sorted(os.listdir(base)):
            if os.path.isfile(os.path.join(base, f)) or os.path.islink(os.path.join(base, f)):
                lower = f.lower()
                if lower.endswith(".mkv") or lower.endswith(".mp4"):
                    eps.append(f)
    except FileNotFoundError:
        pass
    return eps

# streaming helper: run command and stream stdout line by line
def stream_cmd(cmd):
    # cmd should be a list
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for line in iter(proc.stdout.readline, ''):
            yield line
    finally:
        proc.stdout.close()
        proc.wait()
        yield f"\n---- process exited with code {proc.returncode} ----\n"

@app.route('/')
def index():
    shows = list_shows()
    movies = list_movies()
    return render_template('index.html', shows=shows, movies=movies)

@app.route('/show/<path:show>')
def show_page(show):
    # show is URL path encoded; it's fine
    seasons = list_seasons(show)
    return render_template('show.html', show=show, seasons=seasons, list_episodes=list_episodes)

# STATIC (CSS)
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)

# Endpoints to run scripts (streaming)
@app.route('/run/refresh_show', methods=['POST'])
def refresh_show():
    show = request.form.get('show', '').strip()
    if not show:
        return "Missing show", 400

    # Call both 4k and 1080 variants sequentially
    def gen():
        yield f"=== Refreshing show: {show} (4K source) ===\n"
        cmd = [SHOWS_SCRIPT, os.path.join(BASENAME_4K, "shows"), "--show", show]
        for out in stream_cmd(cmd):
            yield out

        yield f"\n=== Refreshing show: {show} (1080p source) ===\n"
        cmd2 = [SHOWS_SCRIPT, os.path.join(BASENAME_1080, "shows"), "--show", show]
        for out in stream_cmd(cmd2):
            yield out

    return Response(stream_with_context(gen()), mimetype='text/plain; charset=utf-8')

@app.route('/run/refresh_movie', methods=['POST'])
def refresh_movie():
    movie = request.form.get('movie', '').strip()
    if not movie:
        return "Missing movie", 400

    def gen():
        yield f"=== Refreshing movie: {movie} (4K source) ===\n"
        cmd = [MOVIES_SCRIPT, os.path.join(BASENAME_4K, "movies"), "--movie", movie]
        for out in stream_cmd(cmd):
            yield out

        yield f"\n=== Refreshing movie: {movie} (1080p source) ===\n"
        cmd2 = [MOVIES_SCRIPT, os.path.join(BASENAME_1080, "movies"), "--movie", movie]
        for out in stream_cmd(cmd2):
            yield out

    return Response(stream_with_context(gen()), mimetype='text/plain; charset=utf-8')

@app.route('/run/refresh_all', methods=['POST'])
def refresh_all():
    # full refresh of everything (runs shows+movies for both sources)
    def gen():
        yield "=== Full refresh: Movies 4K ===\n"
        for out in stream_cmd([MOVIES_SCRIPT, os.path.join(BASENAME_4K, "movies"), "--full"]):
            yield out
        yield "\n=== Full refresh: Movies 1080p ===\n"
        for out in stream_cmd([MOVIES_SCRIPT, os.path.join(BASENAME_1080, "movies"), "--full"]):
            yield out
        yield "\n=== Full refresh: Shows 4K ===\n"
        for out in stream_cmd([SHOWS_SCRIPT, os.path.join(BASENAME_4K, "shows"), "--full"]):
            yield out
        yield "\n=== Full refresh: Shows 1080p ===\n"
        for out in stream_cmd([SHOWS_SCRIPT, os.path.join(BASENAME_1080, "shows"), "--full"]):
            yield out

    return Response(stream_with_context(gen()), mimetype='text/plain; charset=utf-8')

@app.route('/run/refresh_movies_inc', methods=['POST'])
def refresh_movies_inc():
    def gen():
        yield "=== Incremental copy: Movies (4K) ===\n"
        for out in stream_cmd([MOVIES_SCRIPT, os.path.join(BASENAME_4K, "movies")]):
            yield out
        yield "\n=== Incremental copy: Movies (1080p) ===\n"
        for out in stream_cmd([MOVIES_SCRIPT, os.path.join(BASENAME_1080, "movies")]):
            yield out
    return Response(stream_with_context(gen()), mimetype='text/plain; charset=utf-8')

@app.route('/run/refresh_shows_inc', methods=['POST'])
def refresh_shows_inc():
    def gen():
        yield "=== Incremental copy: Shows (4K) ===\n"
        for out in stream_cmd([SHOWS_SCRIPT, os.path.join(BASENAME_4K, "shows")]):
            yield out
        yield "\n=== Incremental copy: Shows (1080p) ===\n"
        for out in stream_cmd([SHOWS_SCRIPT, os.path.join(BASENAME_1080, "shows")]):
            yield out
    return Response(stream_with_context(gen()), mimetype='text/plain; charset=utf-8')

# convenience endpoint: redirect to index
@app.route('/ui')
def ui():
    return redirect(url_for('index'))

if __name__ == '__main__':
    # For quick tests only. In production you should run behind gunicorn.
    app.run(host='0.0.0.0', port=8095, debug=False)
