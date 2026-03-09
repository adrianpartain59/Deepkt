"""Spotify OAuth flow and playlist fetching via spotipy."""

import os
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SPOTIFY_SCOPE = "playlist-read-private playlist-read-collaborative"

_sp_oauth: Optional[SpotifyOAuth] = None
_sp_client: Optional[spotipy.Spotify] = None
_token_info: Optional[dict] = None


def _get_redirect_uri() -> str:
    return os.environ.get(
        "SPOTIFY_REDIRECT_URI",
        "http://127.0.0.1:8000/api/spotify/callback",
    )


def _get_oauth() -> SpotifyOAuth:
    global _sp_oauth
    if _sp_oauth is None:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValueError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set as environment variables."
            )
        _sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=_get_redirect_uri(),
            scope=SPOTIFY_SCOPE,
            open_browser=False,
        )
    return _sp_oauth


def get_auth_url() -> str:
    return _get_oauth().get_authorize_url()


def handle_callback(code: str) -> bool:
    """Exchange the auth code for an access token. Returns True on success."""
    global _sp_client, _token_info
    oauth = _get_oauth()
    _token_info = oauth.get_access_token(code, as_dict=True)
    if _token_info:
        _sp_client = spotipy.Spotify(auth=_token_info["access_token"])
        return True
    return False


def _ensure_client() -> spotipy.Spotify:
    """Return a valid Spotify client, refreshing the token if needed."""
    global _sp_client, _token_info
    if _token_info is None or _sp_client is None:
        # Try to recover from spotipy's on-disk cache (survives server restarts)
        oauth = _get_oauth()
        cached = oauth.get_cached_token()
        if cached:
            _token_info = cached
            _sp_client = spotipy.Spotify(auth=_token_info["access_token"])
        else:
            raise ValueError("Not authenticated with Spotify. Sign in first.")
    oauth = _get_oauth()
    if oauth.is_token_expired(_token_info):
        _token_info = oauth.refresh_access_token(_token_info["refresh_token"])
        _sp_client = spotipy.Spotify(auth=_token_info["access_token"])
    return _sp_client


def logout():
    """Clear the in-memory token and delete the on-disk cache."""
    global _sp_client, _token_info
    _sp_client = None
    _token_info = None
    if _sp_oauth and _sp_oauth.cache_path and os.path.exists(_sp_oauth.cache_path):
        os.remove(_sp_oauth.cache_path)


def is_authenticated() -> bool:
    try:
        _ensure_client()
        return True
    except ValueError:
        return False


def get_user_playlists() -> list[dict]:
    """Return the user's playlists as [{id, name, track_count, image_url, owned}]."""
    sp = _ensure_client()
    user_id = sp.current_user()["id"]
    playlists = []
    results = sp.current_user_playlists(limit=50)
    while results:
        for item in results["items"]:
            # Feb 2026 API change: "tracks" field may be null / renamed to "items"
            tracks_info = item.get("tracks") or item.get("items")
            track_count = tracks_info["total"] if tracks_info else 0
            owner = item.get("owner", {})
            playlists.append({
                "id": item["id"],
                "name": item["name"],
                "track_count": track_count,
                "image_url": item["images"][0]["url"] if item.get("images") else None,
                "owned": owner.get("id") == user_id,
            })
        if results.get("next"):
            results = sp.next(results)
        else:
            break
    return playlists


def get_playlist_tracks(playlist_id: str) -> list[dict]:
    """Return all tracks from a playlist as [{artist, title}].

    Uses playlist_items (Feb 2026 /items endpoint). Only works for
    playlists the authenticated user owns or collaborates on — Spotify
    Dev Mode no longer returns track data for followed/public playlists.
    """
    sp = _ensure_client()
    tracks = []
    try:
        results = sp.playlist_items(playlist_id)
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status in (403, 404):
            print(f"[spotify] {e.http_status} for playlist {playlist_id}, skipping")
            return []
        raise
    while results:
        for entry in results.get("items", []):
            # Feb 2026: track data is under "item" key, fall back to "track"
            track = entry.get("item") or entry.get("track")
            if not track or not track.get("artists"):
                continue
            tracks.append({
                "artist": track["artists"][0]["name"],
                "title": track["name"],
            })
        if results.get("next"):
            results = sp.next(results)
        else:
            break
    return tracks
