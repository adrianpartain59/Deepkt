import os
import re
import json
import time
import requests
import yt_dlp
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from deepkt import db as trackdb

CRAWLER_STATE_FILE = "data/crawler_state.json"
CRAWLED_LINKS_FILE = "crawled_links.txt"
DEFAULT_DB_PATH = "data/tracks.db"
MAX_URLS = 10000

class SoundCloudSpider:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = db_path
        self.client_id = None
        self.visited = set()
        self.crawled_urls = set()
        self.console = Console()
        self.load_state()

        # Create output file if missing
        if not os.path.exists(CRAWLED_LINKS_FILE):
             open(CRAWLED_LINKS_FILE, 'w').close()
             
        # Load existing crawled links so we don't duplicate
        with open(CRAWLED_LINKS_FILE, 'r') as f:
             for line in f:
                 url = line.strip()
                 if url and not url.startswith('#'):
                     self.crawled_urls.add(url)
                     
        # Also load existing database tracks to prevent crawling them again
        # conn = trackdb.get_db(self.db_path)
        # tracks = trackdb.get_tracks(conn)
        # for t in tracks:
        #      if 'url' in t and t['url']:
        #          self.crawled_urls.add(t['url'])
        # conn.close()

    def load_state(self):
        if os.path.exists(CRAWLER_STATE_FILE):
            with open(CRAWLER_STATE_FILE, 'r') as f:
                data = json.load(f)
                self.visited = set(data.get("visited", []))
        else:
            self.visited = set()

    def save_state(self):
        with open(CRAWLER_STATE_FILE, 'w') as f:
            json.dump({"visited": list(self.visited)}, f, indent=4)

    def extract_client_id(self):
        self.console.print("  [dim]Fishing for SoundCloud Client ID...[/dim]")
        html = requests.get('https://soundcloud.com', headers={'User-Agent': 'Mozilla/5.0'}).text
        scripts = re.findall(r'<script crossorigin src="([^"]+)"></script>', html)
        
        for s in reversed(scripts):
            try:
                js = requests.get(s).text
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js)
                if match:
                     self.client_id = match.group(1)
                     self.console.print(f"  [dim green]Found Client ID: {self.client_id}[/dim green]")
                     return True
            except:
                continue
        self.console.print("  [bold red]Could not extract client_id![/bold red]")
        return False

    def resolve_user(self, artist_url):
        if not self.client_id:
             if not self.extract_client_id(): return None
             
        res = requests.get(
            f'https://api-v2.soundcloud.com/resolve?url={artist_url}&client_id={self.client_id}', 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        if res.status_code == 200:
            return res.json()
        return None

    def get_followings(self, user_id, limit=10):
        url = f'https://api-v2.soundcloud.com/users/{user_id}/followings?client_id={self.client_id}&limit={limit}'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
             return res.json().get('collection', [])
        return []

    def get_user_likes(self, user_id, limit=50):
        """Fetch a user's liked tracks from the SoundCloud API.

        Returns:
            List of track dicts from the API (each has 'user', 'permalink_url', etc.)
        """
        url = f'https://api-v2.soundcloud.com/users/{user_id}/likes?client_id={self.client_id}&limit={limit}'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
            collection = res.json().get('collection', [])
            # Each item in likes has a 'track' key with the actual track data
            tracks = []
            for item in collection:
                track = item.get('track')
                if track and track.get('permalink_url'):
                    tracks.append(track)
            return tracks
        return []

    def search_playlists(self, query, limit=20):
        """Search SoundCloud for playlists matching a query.

        Args:
            query: Search term (e.g. 'drift phonk').
            limit: Max playlists to return.

        Returns:
            List of playlist dicts with id, title, description, track_count, etc.
        """
        if not self.client_id:
            if not self.extract_client_id():
                return []

        url = (f'https://api-v2.soundcloud.com/search/playlists'
               f'?q={query}&client_id={self.client_id}&limit={limit}')
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
            return res.json().get('collection', [])
        return []

    def get_playlist_tracks(self, playlist_id):
        """Get all tracks from a specific playlist.

        Handles SoundCloud's behavior of returning stub objects (only id)
        for large playlists by batch-resolving them via the /tracks endpoint.

        Args:
            playlist_id: SoundCloud playlist ID.

        Returns:
            List of track dicts with user, permalink_url, duration, etc.
        """
        if not self.client_id:
            if not self.extract_client_id():
                return []

        url = (f'https://api-v2.soundcloud.com/playlists/{playlist_id}'
               f'?client_id={self.client_id}&representation=full')
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code != 200:
            return []

        data = res.json()
        tracks = data.get('tracks', [])

        # Separate full tracks from stubs (stubs only have 'id')
        full_tracks = []
        stub_ids = []
        for t in tracks:
            if t.get('permalink_url') and t.get('user'):
                full_tracks.append(t)
            elif t.get('id'):
                stub_ids.append(str(t['id']))

        # Batch-resolve stubs in groups of 50
        if stub_ids:
            self.console.print(f"      [dim]Resolving {len(stub_ids)} stub tracks...[/dim]")
            for i in range(0, len(stub_ids), 50):
                batch = stub_ids[i:i+50]
                ids_param = ','.join(batch)
                resolve_url = (f'https://api-v2.soundcloud.com/tracks'
                               f'?ids={ids_param}&client_id={self.client_id}')
                r = requests.get(resolve_url, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code == 200:
                    resolved = r.json()
                    full_tracks.extend(resolved)
                time.sleep(0.3)

        return full_tracks

    def scrape_tracks(self, uid, permalink, num_tracks):
        self.console.print(f"    [dim cyan]Extracting top {num_tracks} tracks (API + yt-dlp)...[/dim cyan]")
        extracted = []
        
        # 1. First, grab the top 30 tracks from the API directly
        try:
            import requests
            url = f'https://api-v2.soundcloud.com/users/{uid}/toptracks?client_id={self.client_id}&limit=50&linked_partitioning=1'
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if res.status_code == 200:
                data = res.json()
                for entry in data.get('collection', []):
                    track_url = entry.get('permalink_url')
                    duration_ms = entry.get('duration')
                    if track_url and not '/sets/' in track_url and f"soundcloud.com/{permalink}/" in track_url:
                        if track_url not in self.crawled_urls and track_url not in extracted:
                            if duration_ms is not None and duration_ms > 600000:
                                self.console.print(f"      [dim yellow]Skipping long track ({duration_ms//1000}s): {track_url}[/dim yellow]")
                                continue
                            extracted.append(track_url)
                self.console.print(f"      [green]Extracted {len(extracted)} top tracks via API.[/green]")
        except Exception as e:
            self.console.print(f"      [dim red]Failed API top tracks extraction: {e}[/dim red]")
            
        # 2. Then ask yt-dlp for the remaining chronological tracks up to num_tracks
        chunk_size = 50
        start_index = 1
        max_attempts = 10 # Prevent infinite loops if they simply don't have 100 valid tracks
        attempts = 0
        
        try:
            import subprocess
            import json
            
            while len(extracted) < num_tracks and attempts < max_attempts:
                attempts += 1
                end_index = start_index + chunk_size - 1
                
                # We use yt-dlp --flat-playlist to get their tracks, bypassing the API top-tracks limit & Datadome
                artist_url = f"https://soundcloud.com/{permalink}"
                import sys
                cmd = [
                    sys.executable,
                    "-m", "yt_dlp",
                    "-I", f"{start_index}:{end_index}",
                    "--flat-playlist",
                    "--dump-json",
                    artist_url
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                lines = result.stdout.splitlines()
                
                # If yt-dlp returned absolutely nothing, we hit the exact end of their profile
                if not lines:
                    break
                
                for line in lines:
                    if not line.strip(): continue
                    try:
                        entry = json.loads(line)
                        track_url = entry.get('url')
                        duration_ms = entry.get('duration', 0) * 1000 if entry.get('duration') else None
                        
                        # Use urlparse to properly check the path, preventing trailing slash issues
                        from urllib.parse import urlparse
                        if track_url and not '/sets/' in track_url:
                             parsed = urlparse(track_url)
                             # The path should start with /permalink/ (e.g. /lxst_cxntury/track-name)
                             # but might just be exactly the permalink in some edge cases
                             path_parts = parsed.path.strip('/').split('/')
                             if len(path_parts) >= 2 and path_parts[0].lower() == permalink.lower():
                                 if track_url not in self.crawled_urls and track_url not in extracted:
                                     # Skip songs longer than 10 minutes
                                     if duration_ms is not None and duration_ms > 600000:
                                         self.console.print(f"      [dim yellow]Skipping long track ({duration_ms//1000}s): {track_url}[/dim yellow]")
                                         continue
                                     
                                     extracted.append(track_url)
                                     if len(extracted) >= num_tracks:
                                          break
                    except json.JSONDecodeError:
                        continue
                
                # Move the pagination cursor forward for the next loop
                start_index += chunk_size
                
        except Exception as e:
            self.console.print(f"    [bold red]yt-dlp extraction failed: {e}[/bold red]")
            
        return extracted

    def append_links(self, urls):
        with open(CRAWLED_LINKS_FILE, 'a') as f:
            for u in urls:
                f.write(f"{u}\n")
                self.crawled_urls.add(u)

    def determine_tier(self, followers):
        # The user wants exactly 130 tracks per seed artist (30 Top Tracks + 100 Recent)
        return 130

    def get_seed_artists(self):
        results = set()
        
        # Original seeds
        seed_file = "seed_artists.txt"
        if os.path.exists(seed_file):
            with open(seed_file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):
                        results.add(url)
        else:
            self.console.print(f"[bold yellow]Warning: {seed_file} not found![/bold yellow]")
            
        # Newly promoted discovery seeds
        discovery_file = "discovery_seeds.txt"
        if os.path.exists(discovery_file):
            with open(discovery_file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):
                        results.add(url)
                        
        return list(results)

    def crawl(self):
        self.console.print(f"\n[bold magenta]🕷️  Starting SoundCloud Spider[/bold magenta] (Target: {MAX_URLS} new URLs)")
        
        if not self.client_id and not self.extract_client_id():
             self.console.print("[bold red]Spider aborted: No Client ID.[/bold red]")
             return
             
        seeds = self.get_seed_artists()
        self.console.print(f"Loaded [bold cyan]{len(seeds)}[/bold cyan] unique Seed Artists from seed_artists.txt.\n")
        
        new_url_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="magenta", finished_style="green"),
            TaskProgressColumn(),
            TextColumn("({task.completed}/{task.total} URLs)"),
            console=self.console,
        ) as progress:
            
            crawl_task = progress.add_task("[cyan]Crawling Network...", total=MAX_URLS)
            
            # Level 0 (Evaluating Seeds -> Getting their Followings)
            for seed_url in seeds:
                if new_url_count >= MAX_URLS:
                     self.console.print("\n[bold green]✅ Reached 1000 max URL cap. Crawler stopping.[/bold green]")
                     break
                     
                if seed_url in self.visited:
                     continue
                     
                self.console.print(f"\n[bold yellow]🌱 SEED:[/bold yellow] Evaluating {seed_url}...")
                
                user_data = self.resolve_user(seed_url)
                if not user_data:
                    self.console.print(f"  [dim red]SKIP: Could not resolve {seed_url} via API[/dim red]")
                    self.visited.add(seed_url)
                    self.save_state()
                    continue
                    
                uid = user_data.get('id')
                seed_permalink = user_data.get('permalink')
                seed_followers = user_data.get('followers_count', 0)
                
                # Scrape the seed artist's own tracks first!
                self.console.print(f"  [dim cyan]Seed has {seed_followers:,} followers.[/dim cyan]")
                seed_tracks_to_grab = self.determine_tier(seed_followers)
                if seed_tracks_to_grab > 0:
                     self.console.print(f"  [green]SEED TIER HIT:[/green] Authorized for {seed_tracks_to_grab} tracks.")
                     seed_tracks = self.scrape_tracks(uid, seed_permalink, seed_tracks_to_grab)
                     if seed_tracks:
                          self.append_links(seed_tracks)
                          new_url_count += len(seed_tracks)
                          progress.update(crawl_task, advance=len(seed_tracks))
                          self.console.print(f"  [bold green]SAVED:[/bold green] Stored {len(seed_tracks)} tracks from seed. (Total new: {new_url_count})")
                     else:
                          self.console.print("  [dim yellow]EMPTY: yt-dlp returned 0 original tracks for seed.[/dim yellow]")
                               
                self.visited.add(seed_url)
                self.save_state()
                
        self.console.print(f"\n[bold magenta]🕸️ Spider Sleep.[/bold magenta] Added {new_url_count} tracks to {CRAWLED_LINKS_FILE}.")

def extract_artist_urls(artist_url, num_tracks=130):
    """
    Standalone function to extract up to `num_tracks` for a specific artist.
    Useful for UI-driven extraction of a single artist.
    """
    spider = SoundCloudSpider()
    if not spider.client_id and not spider.extract_client_id():
        raise ValueError("Could not extract SoundCloud Client ID. SoundCloud may be blocking requests.")
        
    user_data = spider.resolve_user(artist_url)
    if not user_data:
        raise ValueError(f"Could not resolve the artist URL. Please verify the link is valid: {artist_url}")
        
    uid = user_data.get('id')
    permalink = user_data.get('permalink')
    
    # Clear crawled_urls so it doesn't skip tracks that might have been discovered but not pipeline'd
    spider.crawled_urls = set()
    
    extracted = spider.scrape_tracks(uid, permalink, num_tracks)
    if not extracted:
        raise ValueError(f"No valid tracks found for artist {permalink}.")
        
    return extracted
