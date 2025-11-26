import os
import time
import json
from pathlib import Path
import threading

import requests
from flask import Flask, send_file
from prometheus_client import Gauge, start_http_server
from dotenv import load_dotenv

# === Paths & env ===
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# === CONFIG FROM ENV ===
STATS_FILE_DEFAULT = os.getenv(
    "NEST_STATS_FILE", str(BASE_DIR / "song_play_stats.json")
)
JSON_STATS_PATH = os.getenv(
    "NEST_TOP10_JSON_STATS_PATH", STATS_FILE_DEFAULT
)
LOCAL_DIR = os.getenv(
    "NEST_TOP10_LOCAL_DIR", str(BASE_DIR / "top10_album_arts")
)
CHECK_INTERVAL = int(os.getenv("NEST_TOP10_CHECK_INTERVAL", "30"))

METRICS_PORT = int(os.getenv("NEST_TOP10_METRICS_PORT", "9808"))
IMAGE_PORT = int(os.getenv("NEST_TOP10_IMAGE_PORT", "9809"))

BGS_DIR = os.getenv(
    "NEST_TOP10_BGS_DIR", str(BASE_DIR / "bgs_nest_top_ten")
)

# === SETUP ===
os.makedirs(LOCAL_DIR, exist_ok=True)
os.makedirs(BGS_DIR, exist_ok=True)

# Dynamically create unique-label metrics and tracking for previous label values
song_top_metrics = []
previous_labels = []  # store dicts of {label_name: value}

for i in range(10):
    rank = i + 1
    label_names = [f"title{rank}", f"artist{rank}", f"album{rank}"]
    gauge = Gauge(
        f"song_top{rank}_most_played",
        "Top played song",
        label_names,
    )
    song_top_metrics.append(gauge)
    previous_labels.append({})  # init empty previous label dict

# === Flask App for Image Serving ===
images_app = Flask("images_app")


@images_app.route("/current_art_<int:rank>.jpg")
def serve_top_image(rank: int):
    if 1 <= rank <= 10:
        path = os.path.join(LOCAL_DIR, f"current_art_{rank}.jpg")
        if os.path.exists(path):
            return send_file(path, mimetype="image/jpeg")
        return f"Image {rank} not found", 404
    return "Invalid rank", 400


@images_app.route("/bgs/<path:filename>")
def serve_background_image(filename: str):
    path = os.path.join(BGS_DIR, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    return f"Background image '{filename}' not found", 404


def update_top_10():
    # Wait until stats file exists
    while not os.path.exists(JSON_STATS_PATH):
        print(
            f"[!] Waiting for {JSON_STATS_PATH} to become available..."
        )
        time.sleep(5)

    last_top10_keys = []

    while True:
        try:
            with open(JSON_STATS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            sorted_songs = sorted(
                data.values(),
                key=lambda x: (-x["play_count"], x["title"]),
            )[:10]

            new_top10_keys = [
                f'{song["title"]}::{song["artist"]}::{song["album"]}'
                for song in sorted_songs
            ]

            if new_top10_keys != last_top10_keys:
                print(
                    "[*] Detected new top 10 list. "
                    "Updating images and metrics..."
                )
                last_top10_keys = new_top10_keys

                for i, song in enumerate(sorted_songs):
                    rank = i + 1
                    label_dict = {
                        f"title{rank}": song["title"],
                        f"artist{rank}": song["artist"],
                        f"album{rank}": song["album"],
                    }

                    # Remove old label set if present
                    prev = previous_labels[i]
                    if prev:
                        try:
                            song_top_metrics[i].remove(
                                prev[f"title{rank}"],
                                prev[f"artist{rank}"],
                                prev[f"album{rank}"],
                            )
                        except KeyError:
                            # If labels not present, just ignore
                            pass

                    # Download and store album art
                    img_path = os.path.join(
                        LOCAL_DIR, f"current_art_{rank}.jpg"
                    )
                    try:
                        img_url = song.get("album_art_url", "")
                        if img_url:
                            img_resp = requests.get(
                                img_url, stream=True, timeout=5
                            )
                            if img_resp.status_code == 200:
                                with open(img_path, "wb") as f_img:
                                    for chunk in img_resp.iter_content(1024):
                                        f_img.write(chunk)
                            else:
                                print(
                                    f"[!] Failed to fetch image "
                                    f"{img_url} - Status: "
                                    f"{img_resp.status_code}"
                                )
                        else:
                            print(
                                f"[!] No album_art_url for '{song['title']}'"
                            )
                    except Exception as e:
                        print(
                            f"[!] Failed to fetch image for "
                            f"{song['title']}: {e}"
                        )

                    # Set new label and update play count
                    song_top_metrics[i].labels(
                        **label_dict
                    ).set(song["play_count"])
                    previous_labels[i] = label_dict

        except Exception as e:
            print(f"[!] Error while updating top 10: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    print(
        f"[*] Starting Prometheus /metrics server "
        f"on port {METRICS_PORT}"
    )
    start_http_server(METRICS_PORT)

    print(
        f"[*] Starting Flask image server on port {IMAGE_PORT}"
    )
    threading.Thread(target=update_top_10, daemon=True).start()
    images_app.run(
        host="0.0.0.0", port=IMAGE_PORT, debug=False, use_reloader=False
    )
