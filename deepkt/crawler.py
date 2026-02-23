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
MAX_URLS = 1000

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
        conn = trackdb.get_db(self.db_path)
        tracks = trackdb.get_tracks(conn)
        for t in tracks:
             if 'url' in t and t['url']:
                 self.crawled_urls.add(t['url'])
        conn.close()

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

    def scrape_tracks(self, artist_url, permalink, num_tracks):
        self.console.print(f"    [dim cyan]Extracting top {num_tracks} tracks using yt-dlp...[/dim cyan]")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': num_tracks * 3  # Fetch extra to account for dropped reposts
        }
        extracted = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(artist_url, download=False)
                if not info or 'entries' not in info:
                     return []
                     
                for entry in info['entries']:
                    url = entry.get('url')
                    # Ensure it's original (starts with artist url path)
                    # And prevent getting "likes" or other pages
                    if url and not '/sets/' in url and f"soundcloud.com/{permalink}/" in url:
                         if url not in self.crawled_urls:
                             extracted.append(url)
                             if len(extracted) >= num_tracks:
                                  break
        except Exception as e:
            self.console.print(f"    [bold red]yt-dlp extraction failed: {e}[/bold red]")
        return extracted

    def append_links(self, urls):
        with open(CRAWLED_LINKS_FILE, 'a') as f:
            for u in urls:
                f.write(f"{u}\n")
                self.crawled_urls.add(u)

    def determine_tier(self, followers):
        if followers > 50000: return 50
        elif followers >= 10000: return 35
        elif followers >= 1000: return 20
        return 0

    def get_seed_artists(self):
        conn = trackdb.get_db(self.db_path)
        c = conn.cursor()
        c.execute("SELECT DISTINCT artist, url FROM tracks WHERE status='INDEXED' AND url IS NOT NULL")
        results = set()
        for row in c.fetchall():
            url = row[1]
            if url:
                 parts = url.split('/')
                 if len(parts) >= 4 and 'soundcloud.com' in parts[2]:
                     artist_url = "/".join(parts[:4])
                     results.add(artist_url)
        conn.close()
        return list(results)

    def crawl(self):
        self.console.print(f"\n[bold magenta]🕷️  Starting SoundCloud Spider[/bold magenta] (Target: {MAX_URLS} new URLs)")
        
        if not self.client_id and not self.extract_client_id():
             self.console.print("[bold red]Spider aborted: No Client ID.[/bold red]")
             return
             
        seeds = self.get_seed_artists()
        self.console.print(f"Loaded [bold cyan]{len(seeds)}[/bold cyan] unique Seed Artists from SQLite database.\n")
        
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
                     seed_tracks = self.scrape_tracks(seed_url, seed_permalink, seed_tracks_to_grab)
                     if seed_tracks:
                          self.append_links(seed_tracks)
                          new_url_count += len(seed_tracks)
                          progress.update(crawl_task, advance=len(seed_tracks))
                          self.console.print(f"  [bold green]SAVED:[/bold green] Stored {len(seed_tracks)} tracks from seed. (Total new: {new_url_count})")
                     else:
                          self.console.print("  [dim yellow]EMPTY: yt-dlp returned 0 original tracks for seed.[/dim yellow]")
                
                # Get similar artists (Level 1)
                followings = self.get_followings(uid, limit=10)
                self.console.print(f"  Found {len(followings)} following networks.")
                
                for sim in followings:
                     if new_url_count >= MAX_URLS: break
                     
                     sim_permalink = sim.get('permalink')
                     sim_url = f"https://soundcloud.com/{sim_permalink}"
                     sim_followers = sim.get('followers_count', 0)
                     
                     if sim_url in self.visited:
                          continue
                          
                     self.console.print(f"  -> [bold]SIMILAR:[/bold] {sim.get('username')} ([cyan]{sim_followers:,}[/cyan] followers)")
                     
                     tracks_to_grab = self.determine_tier(sim_followers)
                     if tracks_to_grab == 0:
                          self.console.print("        [dim]SKIP: Too small (<1000 followers).[/dim]")
                     else:
                          self.console.print(f"        [green]TIER HIT:[/green] Authorized for {tracks_to_grab} tracks.")
                          tracks = self.scrape_tracks(sim_url, sim_permalink, tracks_to_grab)
                          if tracks:
                               self.append_links(tracks)
                               new_url_count += len(tracks)
                               progress.update(crawl_task, advance=len(tracks))
                               self.console.print(f"        [bold green]SAVED:[/bold green] Stored {len(tracks)} tracks. (Total new: {new_url_count})")
                          else:
                               self.console.print("        [dim yellow]EMPTY: yt-dlp returned 0 original tracks (all reposts/blocked).[/dim yellow]")
                               
                     self.visited.add(sim_url)
                     self.save_state()
                     time.sleep(1) # Be polite to SoundCloud
                     
                self.visited.add(seed_url)
                self.save_state()
                
        self.console.print(f"\n[bold magenta]🕸️ Spider Sleep.[/bold magenta] Added {new_url_count} tracks to {CRAWLED_LINKS_FILE}.")
