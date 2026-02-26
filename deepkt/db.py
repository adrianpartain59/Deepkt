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
            source          TEXT DEFAULT 'manual',
            status          TEXT DEFAULT 'DISCOVERED',
            error_message   TEXT,
            discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            indexed_at      TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            label           INTEGER NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_status ON tracks(status);
        CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist);
        CREATE INDEX IF NOT EXISTS idx_pairs ON training_pairs(anchor_id, candidate_id);
    """)
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


def get_all_features(conn):
    """Get all stored features with track metadata.

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


def get_tracks_missing_features(conn):
    """Find tracks that have been analyzed but are missing some extractors.

    Useful when new extractors are added and old tracks need re-analysis.

    Returns:
        List of track IDs.
    """
    from deepkt.features import ALL_EXTRACTOR_NAMES
    expected_count = len(ALL_EXTRACTOR_NAMES)

    rows = conn.execute(
        "SELECT track_id FROM track_features WHERE extractor_count < ?",
        (expected_count,)
    ).fetchall()
    return [row["track_id"] for row in rows]
