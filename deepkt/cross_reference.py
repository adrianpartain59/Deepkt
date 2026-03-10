"""Cross-reference Spotify (artist, title) pairs against SoundCloud track search.

For each pair, search SoundCloud for the track, confirm both artist name and
track title match, and collect the artist's SoundCloud profile URL.
"""

import os
import time
import unicodedata
import re
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console

from deepkt.crawler import SoundCloudSpider

SEED_OUTPUT_FILE = "data/spotify_seed_artists.txt"


@dataclass
class CrossRefProgress:
    total: int = 0
    processed: int = 0
    matched: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    state: str = "idle"
    error: str = ""
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "total": self.total,
            "processed": self.processed,
            "matched_count": len(self.matched),
            "unmatched_count": len(self.unmatched),
            "matched": self.matched,
            "unmatched": self.unmatched,
            "error": self.error,
        }


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _compact(text: str) -> str:
    """Normalize then strip all spaces — catches 'Chief Keef' vs 'ChiefKeef'."""
    return _normalize(text).replace(" ", "")


def _names_match(a: str, b: str) -> bool:
    # Exact normalized match
    if _normalize(a) == _normalize(b):
        return True
    # Space-collapsed match (e.g. "Chief Keef" vs "ChiefKeef")
    if _compact(a) == _compact(b):
        return True
    # One name contains the other (e.g. "SpaceGhostPurrpArchive" contains "SpaceGhostPurrp")
    na, nb = _compact(a), _compact(b)
    if len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na):
        return True
    return False


def _titles_match(spotify_title: str, sc_title: str) -> bool:
    """Fuzzy title match: normalized Spotify title must appear in normalized SC title.

    SoundCloud titles often have extra suffixes like "(Official Audio)" or
    "[Prod. XYZ]", so a contains-check is more forgiving than strict equality.
    """
    return _normalize(spotify_title) in _normalize(sc_title)


def cross_reference_tracks(
    track_pairs: list[dict],
    spider: Optional[SoundCloudSpider] = None,
    rate_limit: float = 1.0,
    progress: Optional[CrossRefProgress] = None,
) -> CrossRefProgress:
    """Search SoundCloud for each (artist, title) pair and collect matched artist URLs.

    Args:
        track_pairs: List of {"artist": str, "title": str} dicts.
        spider: Existing SoundCloudSpider instance (created if None).
        rate_limit: Seconds to pause between SoundCloud API calls.
        progress: Shared progress object (created if None).

    Returns:
        CrossRefProgress with matched/unmatched results.
    """
    console = Console()

    if spider is None:
        spider = SoundCloudSpider()

    if progress is None:
        progress = CrossRefProgress()

    seen_artists: dict[str, str] = {}
    unique_pairs: list[dict] = []
    for pair in track_pairs:
        key = _normalize(pair["artist"])
        if key in seen_artists:
            continue
        unique_pairs.append(pair)
        seen_artists[key] = ""

    progress.total = len(unique_pairs)
    progress.state = "running"

    console.print(
        f"\n[bold cyan]Cross-referencing {progress.total} unique artists on SoundCloud...[/bold cyan]"
    )

    for pair in unique_pairs:
        if progress.cancelled:
            progress.state = "done"
            return progress

        artist = pair["artist"]
        title = pair["title"]
        norm_artist = _normalize(artist)

        if norm_artist in seen_artists and seen_artists[norm_artist]:
            progress.processed += 1
            continue

        query = f"{artist} {title}"
        results = spider.search_tracks(query, limit=5)

        matched = False
        for result in results:
            sc_user = result.get("user", {})
            sc_username = sc_user.get("username", "")
            sc_title = result.get("title", "")
            sc_profile_url = sc_user.get("permalink_url", "")

            if _names_match(artist, sc_username) and _titles_match(title, sc_title) and sc_profile_url:
                if not seen_artists.get(norm_artist):
                    seen_artists[norm_artist] = sc_profile_url
                    progress.matched.append({
                        "artist": artist,
                        "sc_url": sc_profile_url,
                        "sc_username": sc_username,
                    })
                    console.print(
                        f"  [green]MATCH:[/green] {artist} -> {sc_profile_url}"
                    )
                matched = True
                break

        if not matched:
            progress.unmatched.append({"artist": artist, "title": title})
            console.print(f"  [dim red]MISS:[/dim red] {artist} - {title}")

        progress.processed += 1
        time.sleep(rate_limit)

    progress.state = "done"
    console.print(
        f"\n[bold cyan]Cross-reference complete:[/bold cyan] "
        f"[green]{len(progress.matched)} matched[/green], "
        f"[red]{len(progress.unmatched)} unmatched[/red]"
    )

    return progress


def save_seed_artists(progress: CrossRefProgress, filepath: str = SEED_OUTPUT_FILE):
    """Write deduplicated artist profile URLs to a file, one per line."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    urls = []
    seen = set()
    for m in progress.matched:
        url = m["sc_url"]
        if url not in seen:
            seen.add(url)
            urls.append(url)

    with open(filepath, "w") as f:
        f.write(f"# Spotify-imported seed artists ({len(urls)} total)\n")
        for url in urls:
            f.write(f"{url}\n")

    return urls
