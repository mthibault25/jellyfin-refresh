#!/usr/bin/env python3
# /opt/docker/webapp/app.py

import os
from flask import Flask, render_template, request, Response, stream_with_context, send_from_directory, url_for, redirect

# Import unified sync engine
from scripts import media_sync

# Media watcher
from scripts import auto_runner
import threading

from pathlib import Path

from config import (
    DEST_MOVIES,
    DEST_TV,
)

app = Flask(__name__, static_folder='static', template_folder='templates')

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
    return safe_listdir(DEST_TV)

def list_movies():
    return safe_listdir(DEST_MOVIES)

def list_movie(movie):
    base = os.path.join(DEST_MOVIES, movie)

    movies = []
    try:
        for f in sorted(os.listdir(base)):
            p = os.path.join(base, f)

            if os.path.isfile(p) or os.path.islink(p):
                if f.lower().endswith((".mkv", ".mp4")):
                    movies.append(f)
    except FileNotFoundError:
        return []

    return movies


def list_seasons(show):
    base = os.path.join(DEST_TV, show)
    try:
        return sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    except FileNotFoundError:
        return []

def list_episodes(show, season):
    base = os.path.join(DEST_TV, show, season)
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
    movie_dir = DEST_MOVIES / movie
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

from urllib.parse import unquote

@app.route('/movie/<path:movie>')
def movie_page(movie):
    from urllib.parse import unquote
    movie = unquote(movie)

    files = list_movie(movie)

    return render_template(
        'movie.html',
        movie=movie,
        files=files
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
        for line in media_sync.sync_show(show_name=show):
            yield line

    return stream_python(gen)

@app.route('/run/refresh_movie', methods=['POST'])
def refresh_movie():
    movie = request.form.get('movie', '').strip()
    if not movie:
        return "Missing movie", 400

    def gen():
        for line in media_sync.sync_movie(movie_name=movie):
            yield line

    return stream_python(gen)


@app.route('/run/refresh_all', methods=['POST'])
def refresh_all():
    def gen():
        for line in media_sync.sync_all(full=True):
            yield line

    return stream_python(gen)

@app.route('/run/refresh_movies_inc', methods=['POST'])
def refresh_movies_inc():
    def gen():
        for line in media_sync.sync_movies():
            yield line

    return stream_python(gen)

@app.route('/run/refresh_shows_inc', methods=['POST'])
def refresh_shows_inc():
    def gen():
        for line in media_sync.sync_tv():
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8095, debug=False)
