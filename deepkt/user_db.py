"""
User DB — PostgreSQL backend for users and projects.

Falls back to SQLite (via deepkt.db) when DATABASE_URL is not set (local dev).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

_pg_pool = None


def _use_postgres():
    """Check at call time so load_dotenv() has had a chance to run."""
    return bool(os.environ.get("DATABASE_URL"))


def _get_pg_pool():
    """Lazy-init a psycopg2 connection pool."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool

    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor

    database_url = os.environ["DATABASE_URL"]
    _pg_pool = pool.ThreadedConnectionPool(1, 10, database_url)
    _init_pg_tables()
    return _pg_pool


def _get_pg_conn():
    """Get a connection from the pool."""
    p = _get_pg_pool()
    conn = p.getconn()
    return conn


def _put_pg_conn(conn):
    """Return a connection to the pool."""
    _get_pg_pool().putconn(conn)


def _init_pg_tables():
    """Create user/project tables in PostgreSQL if they don't exist."""
    conn = _get_pg_pool().getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              TEXT PRIMARY KEY,
                email           TEXT UNIQUE NOT NULL,
                display_name    TEXT,
                password_hash   TEXT,
                auth_provider   TEXT DEFAULT 'email',
                provider_id     TEXT,
                refresh_token   TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                slot        INTEGER NOT NULL,
                name        TEXT NOT NULL,
                playlist_urls TEXT DEFAULT '[]',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, slot)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
                ON users(auth_provider, provider_id) WHERE provider_id IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);

            CREATE TABLE IF NOT EXISTS liked_tracks (
                user_id     TEXT NOT NULL REFERENCES users(id),
                track_id    TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, track_id)
            );

            CREATE INDEX IF NOT EXISTS idx_liked_tracks_user ON liked_tracks(user_id);
        """)
        # Migration: add llm_output column to projects
        try:
            cur.execute("ALTER TABLE projects ADD COLUMN llm_output TEXT")
        except Exception:
            conn.rollback()
        conn.commit()
    finally:
        _get_pg_pool().putconn(conn)


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

def create_user(email: str, display_name: str = None, password_hash: str = None,
                auth_provider: str = "email", provider_id: str = None) -> dict:
    """Create a new user. Returns the user dict."""
    user_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users (id, email, display_name, password_hash, auth_provider, provider_id, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (user_id, email.lower().strip(), display_name, password_hash, auth_provider, provider_id, now, now),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            """INSERT INTO users (id, email, display_name, password_hash, auth_provider, provider_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, email.lower().strip(), display_name, password_hash, auth_provider, provider_id, now, now),
        )
        conn.commit()
        conn.close()

    return {"id": user_id, "email": email.lower().strip(), "display_name": display_name, "auth_provider": auth_provider}


def get_user_by_email(email: str) -> Optional[dict]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        conn.close()
        return dict(row) if row else None


def get_user_by_provider(provider: str, provider_id: str) -> Optional[dict]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM users WHERE auth_provider = %s AND provider_id = %s",
                (provider, provider_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE auth_provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def store_refresh_token(user_id: str, hashed_jti: str):
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET refresh_token = %s, updated_at = %s WHERE id = %s",
                (hashed_jti, now, user_id),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "UPDATE users SET refresh_token = ?, updated_at = ? WHERE id = ?",
            (hashed_jti, now, user_id),
        )
        conn.commit()
        conn.close()


def revoke_refresh_token(user_id: str):
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET refresh_token = NULL, updated_at = %s WHERE id = %s",
                (now, user_id),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "UPDATE users SET refresh_token = NULL, updated_at = ? WHERE id = ?",
            (now, user_id),
        )
        conn.commit()
        conn.close()


def link_oauth_provider(user_id: str, provider: str, provider_id: str):
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET auth_provider = %s, provider_id = %s, updated_at = %s WHERE id = %s",
                (provider, provider_id, now, user_id),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "UPDATE users SET auth_provider = ?, provider_id = ?, updated_at = ? WHERE id = ?",
            (provider, provider_id, now, user_id),
        )
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Project operations
# ---------------------------------------------------------------------------

def load_user_project(user_id: str, slot: int) -> Optional[dict]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT * FROM projects WHERE user_id = %s AND slot = %s", (user_id, slot)
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["playlist_urls"] = json.loads(d.get("playlist_urls", "[]"))
            if d.get("llm_output"):
                d["llm_output"] = json.loads(d["llm_output"])
            return d
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        row = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? AND slot = ?", (user_id, slot)
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["playlist_urls"] = json.loads(d.get("playlist_urls", "[]"))
        if d.get("llm_output"):
            d["llm_output"] = json.loads(d["llm_output"])
        return d


def save_user_project(user_id: str, slot: int, name: str, playlist_urls: list):
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT id FROM projects WHERE user_id = %s AND slot = %s", (user_id, slot)
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE projects SET name = %s, playlist_urls = %s, updated_at = %s WHERE user_id = %s AND slot = %s",
                    (name, json.dumps(playlist_urls), now, user_id, slot),
                )
            else:
                project_id = uuid.uuid4().hex
                cur.execute(
                    "INSERT INTO projects (id, user_id, slot, name, playlist_urls, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (project_id, user_id, slot, name, json.dumps(playlist_urls), now, now),
                )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        existing = conn.execute(
            "SELECT id FROM projects WHERE user_id = ? AND slot = ?", (user_id, slot)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE projects SET name = ?, playlist_urls = ?, updated_at = ? WHERE user_id = ? AND slot = ?",
                (name, json.dumps(playlist_urls), now, user_id, slot),
            )
        else:
            project_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO projects (id, user_id, slot, name, playlist_urls, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, user_id, slot, name, json.dumps(playlist_urls), now, now),
            )
        conn.commit()
        conn.close()


def delete_user_project(user_id: str, slot: int):
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM projects WHERE user_id = %s AND slot = %s", (user_id, slot))
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute("DELETE FROM projects WHERE user_id = ? AND slot = ?", (user_id, slot))
        conn.commit()
        conn.close()


def save_project_llm_output(user_id: str, slot: int, llm_output: dict):
    """Save LLM analysis output to a project."""
    now = datetime.now(timezone.utc).isoformat()
    llm_json = json.dumps(llm_output)
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE projects SET llm_output = %s, updated_at = %s WHERE user_id = %s AND slot = %s",
                (llm_json, now, user_id, slot),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "UPDATE projects SET llm_output = ?, updated_at = ? WHERE user_id = ? AND slot = ?",
            (llm_json, now, user_id, slot),
        )
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Liked tracks operations
# ---------------------------------------------------------------------------

def get_liked_tracks(user_id: str) -> list[str]:
    """Return list of track IDs liked by user, most-recent-first."""
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT track_id FROM liked_tracks WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        rows = conn.execute(
            "SELECT track_id FROM liked_tracks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        conn.close()
        return [row[0] for row in rows]


def add_liked_track(user_id: str, track_id: str):
    """Like a track. No-op if already liked."""
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO liked_tracks (user_id, track_id, created_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (user_id, track_id, now),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "INSERT OR IGNORE INTO liked_tracks (user_id, track_id, created_at) VALUES (?, ?, ?)",
            (user_id, track_id, now),
        )
        conn.commit()
        conn.close()


def remove_liked_track(user_id: str, track_id: str):
    """Unlike a track."""
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM liked_tracks WHERE user_id = %s AND track_id = %s",
                (user_id, track_id),
            )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute(
            "DELETE FROM liked_tracks WHERE user_id = ? AND track_id = ?",
            (user_id, track_id),
        )
        conn.commit()
        conn.close()


def set_liked_tracks(user_id: str, track_ids: list[str]):
    """Replace all liked tracks for a user (used for bulk sync from client)."""
    now = datetime.now(timezone.utc).isoformat()
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM liked_tracks WHERE user_id = %s", (user_id,))
            for tid in track_ids:
                cur.execute(
                    "INSERT INTO liked_tracks (user_id, track_id, created_at) VALUES (%s, %s, %s)",
                    (user_id, tid, now),
                )
            conn.commit()
        finally:
            _put_pg_conn(conn)
    else:
        from deepkt import db as trackdb
        conn = trackdb.get_db()
        conn.execute("DELETE FROM liked_tracks WHERE user_id = ?", (user_id,))
        for tid in track_ids:
            conn.execute(
                "INSERT INTO liked_tracks (user_id, track_id, created_at) VALUES (?, ?, ?)",
                (user_id, tid, now),
            )
        conn.commit()
        conn.close()
