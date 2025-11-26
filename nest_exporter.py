import os
import time
import threading
import json
from pathlib import Path

import pychromecast
from flask import Flask, jsonify
from prometheus_client import Gauge, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from dotenv import load_dotenv

# === ENV / CONFIG ===
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEVICE_NAME = os.getenv("NEST_DEVICE_NAME", "Nest Mini")
EXPORTER_PORT = int(os.getenv("NEST_EXPORTER_PORT", "9807"))
REFRESH_INTERVAL = int(os.getenv("NEST_REFRESH_INTERVAL", "5"))
STATS_FILE = os.getenv("NEST_STATS_FILE", str(BASE_DIR / "song_play_stats.json"))

# === Prometheus Metrics ===
current_song = Gauge("nest_mini_current_song", "Current song title", ["title"])
current_artist = Gauge("nest_mini_current_artist", "Current artist", ["artist"])
current_album = Gauge("nest_mini_current_album", "Current album", ["album"])
current_status = Gauge("nest_mini_current_status", "Playback status", ["status"])
current_album_art = Gauge(
    "nest_mini_current_album_art_url",
    "Album art URL",
    ["url"],
)
song_play_count = Gauge(
    "nest_mini_song_play_count",
    "Number of times a song has been played",
    ["title", "artist", "album"],
)

app = Flask(__name__)
nowplaying_data = {
    "title": "",
    "artist": "",
    "album": "",
    "album_art_url": "",
    "status": "",
}

# === Persistent storage ===
def load_play_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_play_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


play_stats = load_play_stats()


@app.route("/nowplaying")
def now_playing():
    return jsonify(nowplaying_data)


def fetch_cast_status():
    print("Discovering all Chromecast devices...")
    chromecasts, browser = pychromecast.get_chromecasts()
    cast = next((cc for cc in chromecasts if cc.name == DEVICE_NAME), None)

    if not cast:
        print(f"[ERROR] Could not find Chromecast named '{DEVICE_NAME}'. Found:")
        for cc in chromecasts:
            print(f" - {cc.name}")
        # NOTE: we do NOT stop discovery here; just return.
        return

    print(f"Connected to {cast.name}")
    cast.wait()
    # IMPORTANT: do NOT call browser.stop_discovery() here.
    # Leaving zeroconf running avoids "Zeroconf instance loop must be running" assertions.

    mc = cast.media_controller
    last_song_id = None

    while True:
        try:
            mc.update_status()
            status = mc.status

            title = status.title or "Unknown"
            artist = status.artist or "Unknown"
            album = status.album_name or "Unknown"
            image = status.images[0].url if status.images else ""
            player_state = status.player_state or "UNKNOWN"

            song_id = f"{title}::{artist}::{album}"

            # Update play counts if new song detected (and not Unknown)
            if song_id != last_song_id and title != "Unknown":
                if song_id not in play_stats:
                    play_stats[song_id] = {
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "album_art_url": image,
                        "play_count": 1,
                    }
                else:
                    play_stats[song_id]["play_count"] += 1
                save_play_stats(play_stats)
                last_song_id = song_id

            # Clear old metric values
            current_song._metrics.clear()
            current_artist._metrics.clear()
            current_album._metrics.clear()
            current_status._metrics.clear()
            current_album_art._metrics.clear()
            song_play_count._metrics.clear()

            # Set current info
            current_song.labels(title=title).set(1)
            current_artist.labels(artist=artist).set(1)
            current_album.labels(album=album).set(1)
            current_status.labels(status=player_state).set(1)
            current_album_art.labels(url=image).set(1)

            # Export play counts
            for entry in play_stats.values():
                song_play_count.labels(
                    title=entry["title"],
                    artist=entry["artist"],
                    album=entry["album"],
                ).set(entry["play_count"])

            nowplaying_data.update(
                {
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "album_art_url": image,
                    "status": player_state,
                }
            )

        except Exception as err:
            print(f"[WARN] Error while polling cast: {err}")

        time.sleep(REFRESH_INTERVAL)


if __name__ == "__main__":
    # Mount Prometheus /metrics into the same Flask app
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app,
        {"/metrics": make_wsgi_app()},
    )

    # Run Flask in a background thread
    threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=EXPORTER_PORT,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    ).start()

    # Blocking loop to poll Chromecast
    fetch_cast_status()
