"""
Downloader — yt-dlp wrapper for audio snippet acquisition.

Downloads 30-second snippets (00:30–01:00) from SoundCloud/YouTube URLs,
bypassing intros and tags to capture the core energy of each track.
"""

import os
import glob
import yt_dlp

from yt_dlp.utils import sanitize_filename

def smart_download_range(info_dict, ydl):
    """Dynamically determine the download range based on track duration.

    For tracks longer than 60s, capture 00:30–01:00 (the "drop").
    For shorter tracks, capture the entire duration.
    """
    duration = info_dict.get('duration')
    start, end = 30, 60

    if duration and duration < end:
        return [{'start_time': 0, 'end_time': duration}]

    return [{'start_time': start, 'end_time': end}]


def download_single(url, output_dir="data/tmp"):
    """Download a single track and return metadata.

    Downloads a 30-second MP3 snippet and extracts metadata from yt-dlp.

    Args:
        url: SoundCloud or YouTube URL.
        output_dir: Directory to save MP3 to.

    Returns:
        Dict with keys: file_path, artist, title, url, duration
        Or None if download failed.

    Raises:
        Exception on download failure.
    """
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'download_ranges': smart_download_range,
        'force_keyframes_at_cuts': True,
        'outtmpl': f'{output_dir}/%(uploader)s - %(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    artist = info.get('uploader', 'Unknown')
    title = info.get('title', 'Unknown')
    duration = info.get('duration')
    
    # yt-dlp applies platform-specific sanitization to filenames (e.g. replacing '/' with '⧸')
    # We must replicate this sanitization to find the final MP3 path
    raw_filename = f"{artist} - {title}.mp3"
    filename = sanitize_filename(raw_filename)
    file_path = os.path.join(output_dir, filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"yt-dlp reported success, but no MP3 produced for {url} at {file_path}")

    tags = [t.lower() for t in (info.get('tags', []) or [])]
    genre = (info.get('genre', '') or '').lower()
    if genre and genre not in tags:
        tags.append(genre)

    return {
        "file_path": file_path,
        "filename": filename,
        "artist": artist,
        "title": title,
        "url": url,
        "duration": duration,
        "tags": tags,
    }


def download_snippets(urls, output_dir="data/raw_snippets", quiet=False):
    """Download audio snippets for a list of URLs.

    Args:
        urls: List of SoundCloud/YouTube URLs.
        output_dir: Directory to save MP3 snippets to.
        quiet: If True, suppress yt-dlp output.
    """
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'download_ranges': smart_download_range,
        'force_keyframes_at_cuts': True,
        'outtmpl': f'{output_dir}/%(uploader)s - %(title)s.%(ext)s',
        'quiet': quiet,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(urls)


def download_from_file(links_file="links.txt", output_dir="data/raw_snippets"):
    """Read URLs from a text file and download snippets.

    Args:
        links_file: Path to text file with one URL per line.
        output_dir: Directory to save MP3 snippets to.
    """
    with open(links_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Found {len(urls)} URLs in {links_file}")
    download_snippets(urls, output_dir=output_dir)
