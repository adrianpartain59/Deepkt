"""
DB — SQLite track registry and feature store.

Two tables:
  - tracks: Metadata + processing state for every track
  - track_features: ALL extracted features stored as JSON (43 dims)

Uses WAL mode for concurrent read/write safety.
"""

import json
import sqlite3
from datetime import datetime

DEFAULT_DB_PATH = "data/tracks.db"


def get_db(db_path=DEFAULT_DB_PATH):
    """Get a SQLite connection with WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id              TEXT PRIMARY KEY,
            url             TEXT,
            artist          TEXT NOT NULL,
            title           TEXT NOT NULL,
            tags            TEXT,
            source          TEXT DEFAULT 'manual',
            status          TEXT DEFAULT 'DISCOVERED',
            error_message   TEXT,
            discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            indexed_at      TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            x               REAL,
            y               REAL
        );

        CREATE TABLE IF NOT EXISTS track_features (
            track_id        TEXT PRIMARY KEY REFERENCES tracks(id),
            feature_data    TEXT NOT NULL,
            extractor_count INTEGER,
            extracted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS training_pairs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_id       TEXT NOT NULL REFERENCES tracks(id),
            candidate_id    TEXT NOT NULL REFERENCES tracks(id),
            label           REAL NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS discovery_candidates (
            artist_url      TEXT PRIMARY KEY,
            permalink       TEXT,
            followers       INTEGER DEFAULT 0,
            times_seen      INTEGER DEFAULT 1,
            avg_similarity  REAL,
            status          TEXT DEFAULT 'PENDING',
            discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS discovery_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_url   TEXT NOT NULL,
            probe_track_url TEXT,
            similarity_score REAL,
            nearest_track_id TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT UNIQUE NOT NULL,
            display_name    TEXT,
            password_hash   TEXT,
            auth_provider   TEXT DEFAULT 'email',
            provider_id     TEXT,
            refresh_token   TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id),
            slot        INTEGER NOT NULL,
            name        TEXT NOT NULL,
            playlist_urls TEXT DEFAULT '[]',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, slot)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
            ON users(auth_provider, provider_id) WHERE provider_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        CREATE INDEX IF NOT EXISTS idx_status ON tracks(status);
        CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist);
        CREATE INDEX IF NOT EXISTS idx_pairs ON training_pairs(anchor_id, candidate_id);
        CREATE INDEX IF NOT EXISTS idx_disc_status ON discovery_candidates(status);
        CREATE INDEX IF NOT EXISTS idx_disc_log_candidate ON discovery_log(candidate_url);
    """)

    # Migration: add columns if missing (no-op on fresh databases)
    for col, coltype in [("tags", "TEXT"), ("x", "REAL"), ("y", "REAL")]:
        try:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass

    conn.commit()

def save_training_label(conn, anchor_id, candidate_id, label):
    """Save a triplet label (1=positive, 0=negative) to the database."""
    try:
        conn.execute(
            """INSERT INTO training_pairs (anchor_id, candidate_id, label)
               VALUES (?, ?, ?)""",
            (anchor_id, candidate_id, label)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error saving training label: {e}")


# ============================================================
# Track Management
# ============================================================

def register_track(conn, track_id, artist, title, url=None, source="manual"):
    """Register a new track in the database.

    Idempotent — if track_id already exists, updates the URL if one is provided.
    """
    try:
        conn.execute(
            """INSERT INTO tracks (id, url, artist, title, source) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET url = COALESCE(excluded.url, url)""",
            (track_id, url, artist, title, source),
        )
        conn.commit()
    except sqlite3.Error:
        pass


def update_status(conn, track_id, status, error=None):
    """Update a track's processing status."""
    now = datetime.now().isoformat()
    indexed_at = now if status == "INDEXED" else None

    if indexed_at:
        conn.execute(
            "UPDATE tracks SET status=?, error_message=?, updated_at=?, indexed_at=? WHERE id=?",
            (status, error, now, indexed_at, track_id),
        )
    else:
        conn.execute(
            "UPDATE tracks SET status=?, error_message=?, updated_at=? WHERE id=?",
            (status, error, now, track_id),
        )
    conn.commit()


def get_track(conn, track_id):
    """Get a single track by ID. Returns dict or None."""
    row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    return dict(row) if row else None


def get_tracks(conn, status=None, limit=None):
    """Get tracks, optionally filtered by status.

    Returns:
        List of dicts.
    """
    query = "SELECT * FROM tracks"
    params = []
    if status:
        query += " WHERE status=?"
        params.append(status)
    query += " ORDER BY discovered_at DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def search_tracks(conn, query):
    """Search tracks by artist or title (case-insensitive substring match).

    Returns:
        List of dicts.
    """
    pattern = f"%{query}%"
    rows = conn.execute(
        "SELECT * FROM tracks WHERE artist LIKE ? OR title LIKE ? ORDER BY artist, title",
        (pattern, pattern),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats(conn):
    """Get track counts grouped by status.

    Returns:
        Dict of {status: count} plus 'total'.
    """
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM tracks GROUP BY status"
    ).fetchall()
    stats = {row["status"]: row["count"] for row in rows}
    stats["total"] = sum(stats.values())
    return stats


# ============================================================
# Tag Storage
# ============================================================

def update_tags(conn, track_id, tags_json):
    """Store a JSON array of tag strings for a track.

    Args:
        conn: SQLite connection.
        track_id: Track ID (matches tracks.id).
        tags_json: JSON string of tag array, e.g. '["phonk", "drift"]'.
    """
    conn.execute(
        "UPDATE tracks SET tags = ?, updated_at = ? WHERE id = ?",
        (tags_json, datetime.now().isoformat(), track_id),
    )
    conn.commit()


def get_all_tags(conn):
    """Get tags for all INDEXED tracks that have tags.

    Returns:
        List of dicts: [{track_id, tags}, ...] where tags is a JSON string.
    """
    rows = conn.execute(
        "SELECT id as track_id, tags FROM tracks WHERE status = 'INDEXED' AND tags IS NOT NULL"
    ).fetchall()
    return [dict(row) for row in rows]


# ============================================================
# Feature Storage
# ============================================================

def store_features(conn, track_id, feature_dict):
    """Store the full feature dictionary for a track.

    Args:
        conn: SQLite connection.
        track_id: Track ID (matches tracks.id).
        feature_dict: Dict of {feature_name: [float, ...]} from analyzer.
    """
    json_data = json.dumps(feature_dict)
    extractor_count = len(feature_dict)
    conn.execute(
        "INSERT OR REPLACE INTO track_features (track_id, feature_data, extractor_count) VALUES (?, ?, ?)",
        (track_id, json_data, extractor_count),
    )
    conn.commit()


def get_features(conn, track_id):
    """Get the stored feature dict for a track.

    Returns:
        Dict of {feature_name: [float, ...]} or None.
    """
    row = conn.execute(
        "SELECT feature_data FROM track_features WHERE track_id=?", (track_id,)
    ).fetchone()
    if row:
        return json.loads(row["feature_data"])
    return None


def get_all_metadata(conn):
    """Get all stored track metadata without the heavy features.

    Returns:
        List of dicts: [{track_id, artist, title, url}, ...]
    """
    rows = conn.execute("""
        SELECT id as track_id, artist, title, url
        FROM tracks
        WHERE status = 'INDEXED'
        ORDER BY artist, title
    """).fetchall()

    return [dict(row) for row in rows]

def get_all_features(conn):
    """Get all stored features with track metadata. (Warning: Heavy memory footprint)

    Returns:
        List of dicts: [{track_id, artist, title, feature_data: {...}}, ...]
    """
    rows = conn.execute("""
        SELECT t.id as track_id, t.artist, t.title, t.url, tf.feature_data
        FROM tracks t
        JOIN track_features tf ON t.id = tf.track_id
        WHERE t.status = 'INDEXED'
        ORDER BY t.artist, t.title
    """).fetchall()

    results = []
    for row in rows:
        results.append({
            "track_id": row["track_id"],
            "artist": row["artist"],
            "title": row["title"],
            "url": row["url"],
            "feature_data": json.loads(row["feature_data"]),
        })
    return results




# ============================================================
# Discovery Candidates
# ============================================================

def register_candidate(conn, artist_url, permalink, followers=0):
    """Register or update a discovery candidate artist.

    Idempotent — increments times_seen on conflict.
    """
    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT times_seen FROM discovery_candidates WHERE artist_url = ?",
        (artist_url,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE discovery_candidates SET times_seen = times_seen + 1, updated_at = ? WHERE artist_url = ?",
            (now, artist_url)
        )
    else:
        conn.execute(
            """INSERT INTO discovery_candidates (artist_url, permalink, followers, discovered_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (artist_url, permalink, followers, now, now)
        )
    conn.commit()


def update_candidate_status(conn, artist_url, status, avg_similarity=None):
    """Update a candidate's status and optionally their avg_similarity."""
    now = datetime.now().isoformat()
    if avg_similarity is not None:
        conn.execute(
            "UPDATE discovery_candidates SET status = ?, avg_similarity = ?, updated_at = ? WHERE artist_url = ?",
            (status, avg_similarity, now, artist_url)
        )
    else:
        conn.execute(
            "UPDATE discovery_candidates SET status = ?, updated_at = ? WHERE artist_url = ?",
            (status, now, artist_url)
        )
    conn.commit()


def get_candidates(conn, status=None):
    """Get discovery candidates, optionally filtered by status.

    Returns:
        List of dicts.
    """
    query = "SELECT * FROM discovery_candidates"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY times_seen DESC, discovered_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def log_probe(conn, candidate_url, probe_track_url, similarity, nearest_id):
    """Log an individual probe result for threshold tuning."""
    conn.execute(
        """INSERT INTO discovery_log (candidate_url, probe_track_url, similarity_score, nearest_track_id)
           VALUES (?, ?, ?, ?)""",
        (candidate_url, probe_track_url, similarity, nearest_id)
    )
    conn.commit()


def get_discovery_log(conn, candidate_url=None, limit=100):
    """Get probe history, optionally filtered by candidate.

    Returns:
        List of dicts.
    """
    query = "SELECT * FROM discovery_log"
    params = []
    if candidate_url:
        query += " WHERE candidate_url = ?"
        params.append(candidate_url)
    query += " ORDER BY created_at DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_discovery_stats(conn):
    """Get discovery candidate counts grouped by status.

    Returns:
        Dict of {status: count} plus 'total'.
    """
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM discovery_candidates GROUP BY status"
    ).fetchall()
    stats = {row["status"]: row["count"] for row in rows}
    stats["total"] = sum(stats.values())
    return stats
