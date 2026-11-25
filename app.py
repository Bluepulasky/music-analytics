
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, request
from mutagen import File
import sqlite3
import hashlib
import json
import re
from datetime import datetime
import time
import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
MUSIC_DIR = Path("/mnt/tank-hdd/media/Music").resolve()

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "genre_editor.db"

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg"}

app = Flask(__name__)


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    with get_db() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                album_key TEXT PRIMARY KEY,
                artist TEXT,
                album TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                path TEXT PRIMARY KEY,
                album_key TEXT,
                title TEXT,
                tracknumber TEXT,
                discnumber TEXT,
                genres TEXT,
                mtime REAL,
                size INTEGER
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS reviewed (
                album_key TEXT PRIMARY KEY,
                artist TEXT,
                album TEXT,
                reviewed_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_key TEXT,
                created_at TEXT,
                changes TEXT,
                undone INTEGER DEFAULT 0
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS lastfm_cache (
                cache_key TEXT PRIMARY KEY,
                fetched_at REAL,
                payload TEXT
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracks_album
            ON tracks(album_key)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_edits_album
            ON edits(album_key, undone)
        """)


init_db()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def album_hash(artist, album):
    value = f"{artist}\0{album}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_genres(value):

    if isinstance(value, str):
        values = re.split(r"[;\n]", value)

    elif isinstance(value, list):
        values = value

    else:
        values = []

    result = []
    seen = set()

    for genre in values:

        genre = str(genre).strip()

        if genre and genre.casefold() not in seen:
            result.append(genre)
            seen.add(genre.casefold())

    return result


def track_number(value):

    if not value:
        return 9999

    try:
        return int(str(value).split("/")[0])
    except (ValueError, TypeError):
        return 9999


def read_track(path):

    audio = File(str(path), easy=True)

    if audio is None:
        return None

    artist = (audio.get("artist") or ["Unknown Artist"])[0]
    album = (audio.get("album") or ["Unknown Album"])[0]
    title = (audio.get("title") or [path.stem])[0]

    stat = path.stat()

    return {
        "path": str(path.relative_to(MUSIC_DIR)),
        "artist": artist,
        "album": album,
        "title": title,
        "tracknumber": (audio.get("tracknumber") or [""])[0],
        "discnumber": (audio.get("discnumber") or [""])[0],
        "genres": parse_genres(audio.get("genre", [])),
        "mtime": stat.st_mtime,
        "size": stat.st_size
    }


def write_genres(relative_path, genres):

    path = (MUSIC_DIR / relative_path).resolve()

    if not path.is_relative_to(MUSIC_DIR):
        raise ValueError("Invalid file path")

    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio format")

    audio = File(str(path), easy=True)

    if audio is None:
        raise ValueError(f"Cannot read {relative_path}")

    if genres:
        audio["genre"] = genres
    elif "genre" in audio:
        del audio["genre"]

    audio.save()


# --------------------------------------------------
# LIBRARY INDEX
# --------------------------------------------------

def scan_library():

    started = datetime.now()

    scanned = 0
    updated = 0
    skipped = 0
    errors = 0

    with get_db() as db:

        db.execute("""
            CREATE TEMP TABLE IF NOT EXISTS seen_paths (
                path TEXT PRIMARY KEY
            )
        """)

        db.execute("DELETE FROM seen_paths")

        existing = {
            row["path"]: (row["mtime"], row["size"])
            for row in db.execute(
                "SELECT path, mtime, size FROM tracks"
            )
        }

        for path in MUSIC_DIR.rglob("*"):

            if not path.is_file():
                continue

            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue

            relative_path = str(path.relative_to(MUSIC_DIR))

            try:

                stat = path.stat()

                db.execute(
                    "INSERT INTO seen_paths VALUES (?)",
                    (relative_path,)
                )

                scanned += 1

                old = existing.get(relative_path)

                # No changes: reuse existing metadata
                if old and old == (stat.st_mtime, stat.st_size):
                    skipped += 1
                    continue

                track = read_track(path)

                if not track:
                    continue

                key = album_hash(
                    track["artist"],
                    track["album"]
                )

                db.execute("""
                    INSERT OR REPLACE INTO tracks
                    (path, album_key, title, tracknumber,
                     discnumber, genres, mtime, size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    track["path"],
                    key,
                    track["title"],
                    track["tracknumber"],
                    track["discnumber"],
                    json.dumps(track["genres"], ensure_ascii=False),
                    track["mtime"],
                    track["size"]
                ))

                db.execute("""
                    INSERT OR REPLACE INTO albums
                    (album_key, artist, album)
                    VALUES (?, ?, ?)
                """, (
                    key,
                    track["artist"],
                    track["album"]
                ))

                updated += 1

            except Exception as e:
                errors += 1
                print(f"SCAN ERROR: {path} - {e}")

        # Remove files that no longer exist
        db.execute("""
            DELETE FROM tracks
            WHERE NOT EXISTS (
                SELECT 1 FROM seen_paths
                WHERE seen_paths.path = tracks.path
            )
        """)

        # Remove empty albums
        db.execute("""
            DELETE FROM albums
            WHERE NOT EXISTS (
                SELECT 1 FROM tracks
                WHERE tracks.album_key = albums.album_key
            )
        """)

        db.execute("DROP TABLE seen_paths")

    elapsed = (datetime.now() - started).total_seconds()

    return {
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "seconds": round(elapsed, 2)
    }


# --------------------------------------------------
# ALBUM QUERIES
# --------------------------------------------------

def get_album_list():

    with get_db() as db:

        rows = db.execute("""
            SELECT
                a.album_key,
                a.artist,
                a.album,
                COUNT(t.path) AS tracks,
                CASE WHEN r.album_key IS NOT NULL
                    THEN 1 ELSE 0 END AS reviewed

            FROM albums a

            LEFT JOIN tracks t
                ON t.album_key = a.album_key

            LEFT JOIN reviewed r
                ON r.album_key = a.album_key

            GROUP BY a.album_key

            ORDER BY a.artist COLLATE NOCASE,
                     a.album COLLATE NOCASE
        """).fetchall()

    return [{
        "key": row["album_key"],
        "artist": row["artist"],
        "album": row["album"],
        "tracks": row["tracks"],
        "reviewed": bool(row["reviewed"])
    } for row in rows]


def get_album(key):

    with get_db() as db:

        album = db.execute("""
            SELECT
                a.album_key,
                a.artist,
                a.album,
                CASE WHEN r.album_key IS NOT NULL
                    THEN 1 ELSE 0 END AS reviewed

            FROM albums a

            LEFT JOIN reviewed r
                ON r.album_key = a.album_key

            WHERE a.album_key = ?
        """, (key,)).fetchone()

        if not album:
            return None

        tracks = db.execute("""
            SELECT path, title, tracknumber,
                   discnumber, genres

            FROM tracks

            WHERE album_key = ?

            ORDER BY
                CASE
                    WHEN discnumber = '' THEN 1
                    ELSE CAST(discnumber AS INTEGER)
                END,
                CASE
                    WHEN tracknumber = '' THEN 9999
                    ELSE CAST(tracknumber AS INTEGER)
                END,
                title COLLATE NOCASE
        """, (key,)).fetchall()

    return {
        "key": album["album_key"],
        "artist": album["artist"],
        "album": album["album"],
        "reviewed": bool(album["reviewed"]),
        "tracks": [{
            "path": t["path"],
            "title": t["title"],
            "tracknumber": t["tracknumber"],
            "discnumber": t["discnumber"],
            "genres": json.loads(t["genres"] or "[]")
        } for t in tracks]
    }


# --------------------------------------------------
# LIBRARY API
# --------------------------------------------------

@app.route("/api/tag/albums")
def api_albums():

    albums = get_album_list()

    reviewed = sum(
        1 for album in albums if album["reviewed"]
    )

    return jsonify({
        "albums": albums,
        "total": len(albums),
        "reviewed": reviewed
    })


@app.route("/api/tag/album/<key>")
def api_album(key):

    album = get_album(key)

    if not album:
        return jsonify({"error": "Album not found"}), 404

    return jsonify(album)


@app.route("/api/tag/scan", methods=["POST"])
def api_scan():

    try:
        result = scan_library()
        albums = get_album_list()

        return jsonify({
            "success": True,
            "result": result,
            "total_albums": len(albums)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# REVIEW STATUS
# --------------------------------------------------

@app.route("/api/tag/review", methods=["POST"])
def api_review():

    data = request.get_json() or {}
    key = data.get("album_key")

    album = get_album(key)

    if not album:
        return jsonify({"error": "Album not found"}), 404

    with get_db() as db:

        db.execute("""
            INSERT OR REPLACE INTO reviewed
            (album_key, artist, album, reviewed_at)
            VALUES (?, ?, ?, ?)
        """, (
            key,
            album["artist"],
            album["album"],
            datetime.now().isoformat()
        ))

    return jsonify({"success": True})


# --------------------------------------------------
# SAVE GENRES
# --------------------------------------------------

@app.route("/api/tag/save", methods=["POST"])
def api_save():

    data = request.get_json() or {}

    key = data.get("album_key")
    tracks = data.get("tracks", [])

    album = get_album(key)

    if not album:
        return jsonify({"error": "Album not found"}), 404

    current_tracks = {
        track["path"]: track
        for track in album["tracks"]
    }

    changes = []
    applied = []

    try:

        for item in tracks:

            relative_path = item.get("path")

            if relative_path not in current_tracks:
                raise ValueError("Track does not belong to this album")

            new_genres = parse_genres(item.get("genres", []))
            old_genres = current_tracks[relative_path]["genres"]

            if old_genres == new_genres:
                continue

            changes.append({
                "path": relative_path,
                "old": old_genres,
                "new": new_genres
            })

            write_genres(relative_path, new_genres)
            applied.append(relative_path)

    except Exception as e:

        for relative_path in reversed(applied):

            old = next(
                c["old"] for c in changes
                if c["path"] == relative_path
            )

            try:
                write_genres(relative_path, old)
            except Exception as rollback_error:
                print(f"ROLLBACK ERROR: {rollback_error}")

        return jsonify({
            "error": str(e),
            "rollback_attempted": True
        }), 500

    with get_db() as db:

        for change in changes:

            path = (MUSIC_DIR / change["path"]).resolve()
            stat = path.stat()

            db.execute("""
                UPDATE tracks

                SET genres = ?, mtime = ?, size = ?

                WHERE path = ?
            """, (
                json.dumps(change["new"], ensure_ascii=False),
                stat.st_mtime,
                stat.st_size,
                change["path"]
            ))

        if changes:
            db.execute("""
                INSERT INTO edits
                (album_key, created_at, changes)
                VALUES (?, ?, ?)
            """, (
                key,
                datetime.now().isoformat(),
                json.dumps(changes, ensure_ascii=False)
            ))

        db.execute("""
            INSERT OR REPLACE INTO reviewed
            (album_key, artist, album, reviewed_at)
            VALUES (?, ?, ?, ?)
        """, (
            key,
            album["artist"],
            album["album"],
            datetime.now().isoformat()
        ))

    return jsonify({
        "success": True,
        "modified": len(changes)
    })


# --------------------------------------------------
# UNDO LAST ALBUM EDIT
# --------------------------------------------------

@app.route("/api/tag/undo", methods=["POST"])
def api_undo():

    data = request.get_json() or {}
    key = data.get("album_key")

    with get_db() as db:

        edit = db.execute("""
            SELECT * FROM edits
            WHERE album_key = ? AND undone = 0
            ORDER BY id DESC LIMIT 1
        """, (key,)).fetchone()

        if not edit:
            return jsonify({
                "error": "No changes to undo"
            }), 404

        changes = json.loads(edit["changes"])

        try:

            for change in changes:

                write_genres(
                    change["path"],
                    change["old"]
                )

                path = (MUSIC_DIR / change["path"]).resolve()
                stat = path.stat()

                db.execute("""
                    UPDATE tracks

                    SET genres = ?, mtime = ?, size = ?

                    WHERE path = ?
                """, (
                    json.dumps(change["old"], ensure_ascii=False),
                    stat.st_mtime,
                    stat.st_size,
                    change["path"]
                ))

        except Exception as e:
            return jsonify({"error": str(e)}), 500

        db.execute("""
            UPDATE edits
            SET undone = 1
            WHERE id = ?
        """, (edit["id"],))

    return jsonify({"success": True})

# --------------------------------------------------
# LAST.FM SUGGESTIONS
# --------------------------------------------------

LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_HEADERS = {"User-Agent": "navidrome-style-tagger/0.1 (uso personal)"}
LASTFM_CACHE_DAYS = 30

# Estilos autorizados. Editá libremente (después reiniciá Flask).
def load_generos():
    with open(BASE_DIR / "generos.yaml", "r", encoding="utf-8") as f:
        g = yaml.safe_load(f) or {}
    tier1 = [str(x) for x in g.get("tier1", [])]
    tier2 = [str(c) for hijos in (g.get("tier2") or {}).values() for c in (hijos or [])]
    alias = {str(k): str(v) for k, v in (g.get("alias") or {}).items()}
    return list(dict.fromkeys(tier1 + tier2)), alias

AUTORIZADOS, ALIAS = load_generos()

def norm_tag(tag):
    return re.sub(r"[\s\-_/]+", " ", tag.lower()).strip()


CANON = {norm_tag(g): g for g in AUTORIZADOS}
CANON.update({norm_tag(a): c for a, c in ALIAS.items()})


def lastfm_api_key():
    try:
        with open(BASE_DIR / "config.local.yaml", "r", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {})["lastfm"]["api_key"]
    except (OSError, KeyError, TypeError):
        return None


def lastfm_top_tags(method, refresh=False, **params):
    """Tags de Last.fm como [{"tag", "peso"}], con caché en SQLite."""

    cache_key = json.dumps([method, params], sort_keys=True, ensure_ascii=False)
    now = time.time()

    if not refresh:
        with get_db() as db:
            row = db.execute(
                "SELECT fetched_at, payload FROM lastfm_cache WHERE cache_key = ?",
                (cache_key,)
            ).fetchone()

        if row and now - row["fetched_at"] < LASTFM_CACHE_DAYS * 86400:
            return json.loads(row["payload"])

    r = requests.get(
        LASTFM_URL,
        params={"method": method, "api_key": lastfm_api_key(),
                "format": "json", "autocorrect": 1, **params},
        headers=LASTFM_HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    if "error" in data:
        if data["error"] != 6:   # 6 = no encontrado: se guarda como vacío
            raise RuntimeError(f"Last.fm error {data['error']}: {data.get('message')}")
        tags = []
    else:
        raw = data.get("toptags", {}).get("tag", [])
        if isinstance(raw, dict):   # con un solo tag a veces viene como dict
            raw = [raw]
        tags = sorted(
            ({"tag": t["name"], "peso": int(t["count"])} for t in raw),
            key=lambda t: -t["peso"]
        )

    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO lastfm_cache (cache_key, fetched_at, payload) VALUES (?, ?, ?)",
            (cache_key, now, json.dumps(tags, ensure_ascii=False))
        )

    return tags


def filter_tags(tags):
    """Deja solo los estilos autorizados y recalcula el peso entre ellos."""

    ok, discarded = {}, []

    for t in tags:
        canon = CANON.get(norm_tag(t["tag"]))
        if canon:
            ok[canon] = ok.get(canon, 0) + t["peso"]   # alias y variantes se suman
        else:
            discarded.append(t)

    total = sum(ok.values())

    return {
        "total_tags": len(tags),
        "autorizados": [
            {"estilo": style, "peso_original": weight,
             "porcentaje": round(100 * weight / total, 1)}
            for style, weight in sorted(ok.items(), key=lambda kv: -kv[1])
        ],
        "descartados": discarded[:20]
    }


@app.route("/api/tag/suggestions/<key>")
def api_suggestions(key):

    album = get_album(key)

    if not album:
        return jsonify({"error": "Album not found"}), 404

    if not lastfm_api_key():
        return jsonify({"error": "Falta lastfm.api_key en config.local.yaml"}), 500

    refresh = request.args.get("refresh") == "1"

    try:
        album_tags = lastfm_top_tags(
            "album.getTopTags", refresh=refresh,
            artist=album["artist"], album=album["album"]
        )
        artist_tags = lastfm_top_tags(
            "artist.getTopTags", refresh=refresh,
            artist=album["artist"]
        )
    except Exception as e:
        return jsonify({"error": f"No se pudo consultar Last.fm: {e}"}), 502

    return jsonify({
        "artist": album["artist"],
        "album": album["album"],
        "album_tags": filter_tags(album_tags),
        "artist_tags": filter_tags(artist_tags)
    })

# --------------------------------------------------
# ORIGINAL FLASK ROUTES
# --------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(SITE_DIR, "index.html")


@app.route("/tag")
def tag():
    return send_from_directory(SITE_DIR, "tag.html")

@app.route("/api/tag/status")
def api_status():

    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0]

    return jsonify({"indexed_tracks": count})

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(SITE_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8087)