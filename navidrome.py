import os
import requests
import csv
import logging
from datetime import datetime
from pathlib import Path
import yaml
 
if "__file__" in globals():
    BASE_DIR = Path(__file__).resolve().parent
else:
    BASE_DIR = Path(os.getcwd())

logging.basicConfig(
    filename=BASE_DIR / "data" / "navidrome.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
 
NAVIDROME_URL = "http://192.168.1.99:4533"

config = {}

local_config = BASE_DIR / "config.local.yaml"

with open(local_config, "r") as f:
    config.update(yaml.safe_load(f) or {})

navidrome_cfg = config.get("navidrome", {})

USER = navidrome_cfg.get("user")
PASSWORD = navidrome_cfg.get("password")
 
PARAMS_BASE = {
    "u": USER,
    "p": PASSWORD,
    "v": "1.16.1",
    "c": "stats",
    "f": "json"
}
 
def get(endpoint, extra_params={}):
    r = requests.get(
        f"{NAVIDROME_URL}/rest/{endpoint}",
        params={**PARAMS_BASE, **extra_params}
    )
    r.raise_for_status()
    return r.json()["subsonic-response"]
 
def fetch_navidrome_stats():
    scan = get("getScanStatus")
    total_tracks = scan["scanStatus"]["count"]
 
    artists_data = get("getArtists")
    indexes = artists_data.get("artists", {}).get("index", [])
 
    total_artists = 0
    total_albums = 0
    for index in indexes:
        for artist in index.get("artist", []):
            total_artists += 1
            total_albums += artist.get("albumCount", 0)
 
    stats_file = BASE_DIR / "data" / "navidrome_stats.csv"
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    file_exists = stats_file.exists()
 
    with open(stats_file, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "albums", "tracks", "artists"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d"),
            total_albums,
            total_tracks,
            total_artists
        ])
 
    msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - albums: {total_albums}, tracks: {total_tracks}, artists: {total_artists}"
    logging.info(msg)
    print(msg)
 
if __name__ == "__main__":
    try:
        fetch_navidrome_stats()
    except Exception as e:
        logging.error(f"Error: {e}")
        raise