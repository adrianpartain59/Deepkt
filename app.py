"""
Deepkt — Streamlit UI for sonic similarity search with integrated music player.
"""

import streamlit as st
import logging
# Suppress Streamlit's aggressive background thread warnings that cause terminal stutter
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)
import os
import base64
import tempfile
import threading
import urllib.parse

from deepkt.downloader import download_single, smart_download_range
from deepkt.analyzer import analyze_snippet, build_search_vector
from deepkt.indexer import get_collection, rebuild_search_index, query_similar
from deepkt.config import (
    get_enabled_features, get_search_feature_names, get_search_dimensions,
    load_feature_config,
)
from deepkt import db as trackdb
from deepkt.db import DEFAULT_DB_PATH


# --- Page Config ---
st.set_page_config(
    page_title="Deepkt",
    page_icon="🔊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    :root {
        --accent: #e040fb;
        --accent-dim: #7c4dff;
        --bg-card: rgba(255,255,255,0.04);
        --border: rgba(255,255,255,0.08);
    }
    html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }
    .hero-title {
        font-size: 3.2rem; font-weight: 800;
        background: linear-gradient(135deg, #e040fb 0%, #7c4dff 50%, #00e5ff 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; margin-bottom: 0; letter-spacing: -1px;
    }
    .hero-subtitle {
        text-align: center; color: #888; font-weight: 300;
        font-size: 1.1rem; margin-top: -8px; margin-bottom: 2rem;
    }
    .result-card {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: 14px; padding: 1.2rem 1.4rem; margin-bottom: 0.8rem;
        transition: all 0.25s ease; backdrop-filter: blur(10px);
    }
    .result-card:hover {
        border-color: var(--accent); box-shadow: 0 0 20px rgba(224, 64, 251, 0.15);
        transform: translateY(-2px);
    }
    .result-rank { font-size: 2rem; font-weight: 800; color: var(--accent); line-height: 1; }
    .result-artist { font-size: 1.15rem; font-weight: 600; color: #f0f0f0; }
    .result-title { font-size: 0.95rem; color: #aaa; font-weight: 300; }
    .match-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.85rem; }
    .match-high { background: rgba(0,229,255,0.15); color: #00e5ff; }
    .match-mid  { background: rgba(124,77,255,0.15); color: #b388ff; }
    .match-low  { background: rgba(255,255,255,0.08); color: #888; }
    .section-header {
        font-size: 1.3rem; font-weight: 600; color: #e0e0e0;
        margin-top: 2rem; margin-bottom: 0.8rem; padding-bottom: 0.4rem;
        border-bottom: 1px solid var(--border);
    }
    .player-card {
        background: linear-gradient(135deg, rgba(124,77,255,0.12) 0%, rgba(224,64,251,0.08) 100%);
        border: 1px solid rgba(224,64,251,0.25);
        border-radius: 16px; padding: 1.5rem; margin: 1rem 0;
        backdrop-filter: blur(10px);
    }
    .player-track-name {
        font-size: 1.4rem; font-weight: 600; color: #f0f0f0;
        margin-bottom: 0.3rem;
    }
    .player-track-artist {
        font-size: 1rem; color: #b388ff; font-weight: 400;
        margin-bottom: 1rem;
    }
    .player-position {
        font-size: 0.8rem; color: #666; text-transform: uppercase;
        letter-spacing: 1.5px; margin-bottom: 0.5rem;
    }
# No-op to trigger multi_replace evaluation, but I need to see if there's any other blocking import.

    .now-playing-dot {
        display: inline-block; width: 8px; height: 8px;
        background: #e040fb; border-radius: 50%;
        animation: pulse 1.5s infinite; margin-right: 8px;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.8); }
    }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    hr { border-color: var(--border) !important; }
</style>
""", unsafe_allow_html=True)


# --- Dynamic feature config ---
FEATURE_NAMES = get_search_feature_names()
SEARCH_DIMS = get_search_dimensions()
ENABLED_FEATURES = get_enabled_features()
FEATURE_CONFIG = load_feature_config()

# --- Buffer config ---
BUFFER_SIZE = 5  # Pre-buffer this many clips ahead

@st.cache_data(ttl=60)
def _get_discovered_artists():
    """Fetch and filter newly discovered artists from SQLite, cached to prevent UI freeze."""
    # 1. Load Seed Artists
    seeds = set()
    if os.path.exists("seed_artists.txt"):
        with open("seed_artists.txt", "r") as f:
            for line in f:
                if line.strip():
                    seeds.add(line.strip().lower())
    if os.path.exists("discovery_seeds.txt"):
        with open("discovery_seeds.txt", "r") as f:
            for line in f:
                if line.strip():
                    seeds.add(line.strip().lower())
    
    # 2. Query all artists from the DB
    import sqlite3
    conn = sqlite3.connect("data/tracks.db")
    conn.row_factory = sqlite3.Row
    artist_data = conn.execute('''
        SELECT artist, MAX(url) as sample_url, COUNT(*) as track_count
        FROM tracks
        GROUP BY artist
        ORDER BY track_count DESC
    ''').fetchall()
    
    # 3. Filter out Seed Artists
    discovered = []
    for row in artist_data:
        artist_name = row["artist"]
        sample_url = row["sample_url"]
        track_count = row["track_count"]
        
        if sample_url:
            parts = sample_url.split('/')
            # e.g. https://soundcloud.com/lxst_cxntury/odyssey
            if len(parts) >= 4 and parts[2] == "soundcloud.com":
                profile_url = f"https://soundcloud.com/{parts[3]}".lower()
            else:
                profile_url = ""
                
            if profile_url and profile_url not in seeds:
                discovered.append({
                    "name": artist_name,
                    "profile_url": profile_url,
                    "count": track_count
                })
    conn.close()
    return discovered

BUFFER_SIZE = 5  # Pre-buffer this many clips ahead


# ============================================================
# Audio Player Helper
# ============================================================

def render_audio_player_b64(b64_audio, autoplay=True):
    """Render a looping, auto-playing audio element from pre-cached base64 data."""
    autoplay_attr = "autoplay" if autoplay else ""
    audio_html = f"""
    <audio {autoplay_attr} loop controls style="width: 100%; border-radius: 10px; outline: none;">
        <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
    </audio>
    """
    st.components.v1.html(audio_html, height=60)


def download_clip_for_track(url, tmp_dir):
    """Download a 30s clip for a track and return the file path."""
    try:
        result = download_single(url, output_dir=tmp_dir)
        return result["file_path"]
    except Exception as e:
        return None


def encode_clip_b64(clip_path):
    """Read an MP3 file and return base64-encoded string for instant rendering."""
    try:
        with open(clip_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


def prefill_buffer_sync(playlist, clip_cache, b64_cache, tmp_dir, start_from):
    """Download clips and pre-encode them. Runs in a background thread."""
    for i in range(start_from, min(start_from + BUFFER_SIZE, len(playlist))):
        if i not in clip_cache and playlist[i].get("url"):
            path = download_clip_for_track(playlist[i]["url"], tmp_dir)
            if path:
                clip_cache[i] = path
                b64 = encode_clip_b64(path)
                if b64:
                    b64_cache[i] = b64


def start_background_prefill(playlist, clip_cache, b64_cache, tmp_dir, start_from):
    """Launch a non-blocking background thread to download upcoming clips."""
    t = threading.Thread(
        target=prefill_buffer_sync,
        args=(playlist, clip_cache, b64_cache, tmp_dir, start_from),
        daemon=True,
    )
    t.start()


def cleanup_old_clips(clip_cache, b64_cache, current_index):
    """Remove downloaded clips that are more than 1 position behind current."""
    to_remove = [idx for idx in clip_cache if idx < current_index - 1]
    for idx in to_remove:
        try:
            if os.path.exists(clip_cache[idx]):
                os.remove(clip_cache[idx])
        except OSError:
            pass
        del clip_cache[idx]
        b64_cache.pop(idx, None)

def fetch_lab_batch_async(tmp_dir):
    """Launch a daemon thread to fetch and encode the next training batch for the lab."""
    import threading
    from deepkt import training_lab

    def worker():
        try:
            batch = training_lab.generate_training_batch(tmp_dir)
            if batch and batch["candidates"]:
                training_lab.LAB_BATCH_QUEUE.put(batch)
        finally:
            training_lab.LAB_IS_LOADING = False

    training_lab.LAB_IS_LOADING = True
    t = threading.Thread(target=worker, daemon=True)
    t.start()


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown("### 🗂️ Library")

    conn = trackdb.get_db()
    stats = trackdb.get_stats(conn)
    conn.close()

    collection = get_collection()
    track_count = collection.count()

    st.metric("Indexed Tracks", stats.get("INDEXED", 0))
    st.caption(f"Search: {SEARCH_DIMS} dims ({len(ENABLED_FEATURES)} features)")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧬 Analyze", use_container_width=True, help="Analyze MP3s → store all features"):
            with st.spinner("Analyzing..."):
                from deepkt.indexer import analyze_and_store
                analyze_and_store()
            st.success("Analysis complete!")
            st.rerun()
    with col2:
        if st.button("🔄 Reindex", use_container_width=True, help="Rebuild search index from stored features"):
            with st.spinner("Rebuilding search index..."):
                rebuild_search_index()
            st.success("Search index rebuilt!")
            st.rerun()

    st.markdown("---")

    st.markdown("### 🧠 Neural Network Active")
    st.info(
        "Deepkt is powered by LAION-CLAP (Contrastive Language-Audio Pretraining).\n\n"
        "Audio is analyzed into 512-dimensional semantic embeddings. "
        "Matches are found using cosine distance across the latent space."
    )

    # Player controls in sidebar when active
    if st.session_state.get("player_active"):
        st.markdown("---")
        st.markdown("### 🎵 Now Playing")
        playlist = st.session_state.get("playlist", [])
        idx = st.session_state.get("current_index", 0)
        if idx < len(playlist):
            track = playlist[idx]
            st.markdown(f"**{track['artist']}**")
            st.markdown(f"*{track['title']}*")
            st.caption(f"Track {idx + 1} of {len(playlist)} · {track['match_pct']}% match")

        if st.button("⏹️ Stop Player", use_container_width=True):
            # Clean up all clips
            clip_cache = st.session_state.get("clip_cache", {})
            for path in clip_cache.values():
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            tmp_dir = st.session_state.get("player_tmp_dir", "")
            try:
                if tmp_dir and os.path.isdir(tmp_dir):
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except:
                pass
            for key in ["player_active", "playlist", "current_index", "clip_cache",
                        "b64_cache", "player_tmp_dir", "query_clip_path", "query_track_name"]:
                st.session_state.pop(key, None)
            st.rerun()


# ============================================================
# Main Area
# ============================================================
st.markdown('<p class="hero-title">Deepkt</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-subtitle">Find music that sounds like your music — not what an algorithm thinks you should hear.</p>', unsafe_allow_html=True)


# ============================================================
# Player View (shown when a session is active)
# ============================================================
if st.session_state.get("player_active"):
    playlist = st.session_state["playlist"]
    idx = st.session_state["current_index"]
    clip_cache = st.session_state["clip_cache"]
    b64_cache = st.session_state.setdefault("b64_cache", {})
    tmp_dir = st.session_state["player_tmp_dir"]

    # Kick off background downloads (non-blocking, returns immediately)
    start_background_prefill(playlist, clip_cache, b64_cache, tmp_dir, start_from=idx + 1)

    if idx < len(playlist):
        track = playlist[idx]

        # --- New Search button ---
        if st.button("🏠 New Search", use_container_width=True):
            # Clean up all clips
            for path in clip_cache.values():
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            try:
                if tmp_dir and os.path.isdir(tmp_dir):
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except:
                pass
            for key in ["player_active", "playlist", "current_index", "clip_cache",
                        "player_tmp_dir", "query_clip_path", "query_track_name"]:
                st.session_state.pop(key, None)
            st.rerun()

        # --- Player Card ---
        # Show centroid similarity if available
        seed_sim_html = ""
        seed_sim = track.get("seed_sim")
        if seed_sim is not None:
            color = "#00e5ff" if seed_sim >= 90 else ("#b388ff" if seed_sim >= 80 else "#ff5252")
            seed_sim_html = f"<br><span style='color:{color}; font-size:0.9rem; font-weight:600;'>🎯 Seed Centroid Match: {seed_sim:.1f}%</span>"

        st.markdown(f"""
        <div class="player-card">
            <div class="player-position">
                <span class="now-playing-dot"></span>NOW PLAYING · TRACK {idx + 1} OF {len(playlist)}
            </div>
            <div class="player-track-name">{track['title']}</div>
            <div class="player-track-artist">{track['artist']} · {track['match_pct']}% match{seed_sim_html}</div>
        </div>
        """, unsafe_allow_html=True)

        # --- Audio Player ---
        b64_audio = b64_cache.get(idx)
        if b64_audio:
            render_audio_player_b64(b64_audio)
        elif clip_cache.get(idx) and os.path.exists(clip_cache[idx]):
            # File exists but not yet base64-encoded, encode now (fast, local file read)
            b64_audio = encode_clip_b64(clip_cache[idx])
            if b64_audio:
                b64_cache[idx] = b64_audio
                render_audio_player_b64(b64_audio)
        else:
            st.warning("⏳ Buffering this track...")
            if track.get("url"):
                with st.spinner("Downloading clip..."):
                    path = download_clip_for_track(track["url"], tmp_dir)
                    if path:
                        clip_cache[idx] = path
                        b64_audio = encode_clip_b64(path)
                        if b64_audio:
                            b64_cache[idx] = b64_audio
                        st.rerun()
                    else:
                        st.error("Failed to download clip for this track.")

        # --- Navigation ---
        nav_cols = st.columns([1, 1, 1])
        with nav_cols[0]:
            if idx > 0:
                if st.button("⏮️ Previous", use_container_width=True):
                    st.session_state["current_index"] = idx - 1
                    st.rerun()
        with nav_cols[1]:
            if track.get("url"):
                st.link_button("🔗 Open on SoundCloud", track["url"], use_container_width=True)
        with nav_cols[2]:
            if idx < len(playlist) - 1:
                if st.button("⏭️ Next", use_container_width=True, type="primary"):
                    # Clean up old clips and skip instantly
                    cleanup_old_clips(clip_cache, b64_cache, idx + 1)
                    st.session_state["current_index"] = idx + 1
                    st.rerun()
            else:
                st.button("🏁 End of playlist", use_container_width=True, disabled=True)
                
        # --- Search Tab Triplet Integration ---
        anchor_id = playlist[0].get("id") or playlist[0].get("track_id")
        if idx > 0:
            st.markdown("---")
            st.markdown("##### 🏋️ Training Lab: Rate this Recommendation")
            st.markdown(f"Anchor Track: **{playlist[0]['title']}**")
            
            def _handle_search_rating(rating_val, toast_msg):
                conn = trackdb.get_db()
                from deepkt.db import save_training_label
                a_id = playlist[0].get("id") or playlist[0].get("track_id")
                c_id = track.get("id") or track.get("track_id")
                if a_id and c_id and a_id != "query":
                    save_training_label(conn, a_id, c_id, rating_val)
                    st.toast(toast_msg)
                else:
                    st.toast("⚠️ Cannot rate: Anchor is not indexed yet.", icon="⚠️")
                conn.close()
                if idx < len(playlist) - 1:
                    cleanup_old_clips(clip_cache, b64_cache, idx + 1)
                    st.session_state["current_index"] = idx + 1
                st.rerun()

            rate_cols = st.columns(4)
            with rate_cols[0]:
                if st.button("🟢 Perfect Match", use_container_width=True, key=f"rate_p_{idx}", type="primary"):
                    _handle_search_rating(1.0, "✅ Perfect Match Saved!")
            with rate_cols[1]:
                if st.button("🟡 Medium Match", use_container_width=True, key=f"rate_mp_{idx}"):
                    _handle_search_rating(0.5, "✅ Medium Match Saved!")
            with rate_cols[2]:
                if st.button("🟠 Medium Negative", use_container_width=True, key=f"rate_mn_{idx}"):
                    _handle_search_rating(-0.5, "✅ Medium Negative Saved!")
            with rate_cols[3]:
                if st.button("🔴 Complete Negative", use_container_width=True, key=f"rate_n_{idx}"):
                    _handle_search_rating(-1.0, "✅ Complete Negative Saved!")

    st.markdown("---")

    # --- Upcoming Tracks ---
    st.markdown('<div class="section-header">📋 Up Next</div>', unsafe_allow_html=True)
    for i, track in enumerate(playlist):
        if i == idx:
            # Currently playing
            st.markdown(f"**▶️ {i+1}. {track['artist']} — {track['title']}** ({track['match_pct']}%)")
        elif i > idx:
            buffered = "✅" if i in b64_cache else "⏳"
            st.markdown(f"{buffered} {i+1}. {track['artist']} — {track['title']} ({track['match_pct']}%)")
        else:
            st.markdown(f"~~{i+1}. {track['artist']} — {track['title']}~~ ({track['match_pct']}%)")


# ============================================================
# Search View (shown when no player is active)
# ============================================================
else:
    tab_url, tab_library, tab_clusters, tab_lab, tab_discovery, tab_autocurate = st.tabs([
        "🔗 URL", 
        "📚 Library", 
        "🌌 Clusters", 
        "🏋️ Lab", 
        "⭐ Discover", 
        "🤖 Curate"
    ])

    # --- Tab 1: Search by URL ---
    with tab_url:
        url = st.text_input("Paste a SoundCloud or YouTube URL",
            placeholder="https://soundcloud.com/artist/track")

        if st.button("🔍 Analyze & Find Matches", type="primary", use_container_width=True):
            if not url.strip():
                st.error("Please enter a URL.")
            elif track_count == 0:
                st.error("Your library is empty! Add links to `links.txt`, run **Analyze** then **Reindex**.")
            else:
                # Create a persistent temp dir for clips
                tmp_dir = tempfile.mkdtemp(prefix="deepkt_player_")

                with st.spinner("⬇️ Downloading snippet..."):
                    try:
                        result = download_single(url, output_dir=tmp_dir)
                        downloaded_path = result["file_path"]
                        track_name = f"{result['artist']} - {result['title']}"
                    except Exception as e:
                        st.error(f"Download failed: {e}")
                        st.stop()

                with st.spinner("🧬 Extracting Sonic DNA & Indexing..."):
                    try:
                        feature_dict = analyze_snippet(downloaded_path)
                        
                        # Save the new track to the database
                        from deepkt import db as trackdb
                        from deepkt import indexer
                        import json
                        import os
                        
                        conn = trackdb.get_db()
                        
                        # Create a valid track_id (we use the filename)
                        artist = result["artist"]
                        title = result["title"]
                        track_id = os.path.basename(downloaded_path)
                        
                        # Insert metadata
                        conn.execute(
                            "INSERT OR IGNORE INTO tracks (id, artist, title, url, status) VALUES (?, ?, ?, ?, ?)",
                            (track_id, artist, title, url, "INDEXED")
                        )
                        
                        # Insert features
                        extractor_count = len(feature_dict)
                        conn.execute(
                            "INSERT OR REPLACE INTO track_features (track_id, feature_data, extractor_count) VALUES (?, ?, ?)",
                            (track_id, json.dumps(feature_dict), extractor_count)
                        )
                        conn.commit()
                        conn.close()
                        
                        # Add to the Vector Index
                        collection = indexer.get_collection()
                        search_vector = indexer.build_search_vector(feature_dict)
                        
                        collection.upsert(
                            embeddings=[search_vector],
                            ids=[track_id],
                            metadatas=[{"artist": artist, "title": title, "url": url}]
                        )
                        
                        st.success("Track analyzed and added to your Library!")
                        
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                        st.stop()

                # Query for similar tracks (get 20 for a good playlist)
                search_vector = build_search_vector(feature_dict)
                results = query_similar(
                    search_vector,
                    n_results=min(20, track_count),
                    exclude_id=track_id
                )

                if not results:
                    st.warning("No similar tracks found in your library!")
                    st.stop()

                # Calc centroid similarity
                import numpy as np
                from deepkt.discovery import compute_seed_centroid
                from deepkt.crawler import SoundCloudSpider
                conn = trackdb.get_db()
                s = SoundCloudSpider()
                seed_centroid, _ = compute_seed_centroid(conn, set(s.get_seed_artists()))
                conn.close()
                
                seed_sim_val = None
                if seed_centroid is not None and search_vector:
                    v = np.array(search_vector, dtype=np.float32)
                    norm = np.linalg.norm(v)
                    if norm > 0:
                        v = v / norm
                        seed_sim_val = float(v @ seed_centroid) * 100.0

                # Build the playlist: query track first, then similar tracks
                playlist = [{
                    "id": track_id,
                    "artist": artist,
                    "title": title,
                    "url": url,
                    "match_pct": 100.0,
                    "seed_sim": seed_sim_val
                }] + results

                # Initialize clip cache with the query track (already downloaded)
                clip_cache = {0: downloaded_path}
                b64_cache = {0: encode_clip_b64(downloaded_path)}

                # Pre-buffer the next BUFFER_SIZE clips (synchronous for initial load)
                with st.spinner(f"🎵 Loading player — buffering {BUFFER_SIZE} tracks..."):
                    prefill_buffer_sync(playlist, clip_cache, b64_cache, tmp_dir, start_from=1)

                # Store everything in session state
                st.session_state["player_active"] = True
                st.session_state["playlist"] = playlist
                st.session_state["current_index"] = 0
                st.session_state["clip_cache"] = clip_cache
                st.session_state["b64_cache"] = b64_cache
                st.session_state["player_tmp_dir"] = tmp_dir
                st.session_state["query_track_name"] = track_name
                st.rerun()

    # --- Tab 2: Search from Library ---
    with tab_library:
        if stats.get("INDEXED", 0) == 0:
            st.info("Your library is empty. Add links to `links.txt`, run **Analyze** then **Reindex**.")
        else:
            search_mode = st.radio(
                "Search by",
                ["🎵 Track", "🎤 Artist"],
                horizontal=True,
                key="library_mode",
            )

            conn = trackdb.get_db()
            all_metadata = trackdb.get_all_metadata(conn)
            conn.close()

            # ---- Track Search Mode ----
            if search_mode == "🎵 Track":
                search_query = st.text_input(
                    "🔍 Search your library",
                    placeholder="Type to filter by artist or title...",
                    key="library_search",
                )

                all_tracks = [
                    {"label": f"{t['artist']} - {t['title']}", "index": i}
                    for i, t in enumerate(all_metadata)
                ]

                if search_query.strip():
                    query_lower = search_query.strip().lower()
                    filtered = [t for t in all_tracks if query_lower in t["label"].lower()]
                else:
                    filtered = all_tracks

                if not filtered:
                    st.warning(f"No tracks matching **\"{search_query}\"**")
                else:
                    st.caption(f"Showing {len(filtered)} of {len(all_tracks)} tracks")

                    selected = st.selectbox(
                        "Pick a track",
                        options=[t["label"] for t in filtered],
                        label_visibility="collapsed",
                    )

                    if st.button("🔍 Find Similar Tracks", type="primary", use_container_width=True):
                        sel_entry = next(t for t in filtered if t["label"] == selected)
                        idx = sel_entry["index"]
                        track = all_metadata[idx]

                        tmp_dir = tempfile.mkdtemp(prefix="deepkt_player_")
                        conn = trackdb.get_db()
                        feature_data = trackdb.get_features(conn, track["track_id"])
                        conn.close()

                        search_vector = build_search_vector(feature_data)
                        results = query_similar(
                            search_vector,
                            n_results=min(20, track_count),
                            exclude_id=track["track_id"],
                        )

                        if not results:
                            st.warning("No similar tracks found!")
                            st.stop()

                        # Calc centroid similarity
                        import numpy as np
                        from deepkt.discovery import compute_seed_centroid
                        from deepkt.crawler import SoundCloudSpider
                        conn = trackdb.get_db()
                        s = SoundCloudSpider()
                        seed_centroid, _ = compute_seed_centroid(conn, set(s.get_seed_artists()))
                        conn.close()
                        
                        seed_sim_val = None
                        if seed_centroid is not None and search_vector:
                            v = np.array(search_vector, dtype=np.float32)
                            norm = np.linalg.norm(v)
                            if norm > 0:
                                v = v / norm
                                seed_sim_val = float(v @ seed_centroid) * 100.0

                        playlist = [{
                            "track_id": track["track_id"],
                            "artist": track["artist"],
                            "title": track["title"],
                            "url": track["url"],
                            "match_pct": 100.0,
                            "seed_sim": seed_sim_val
                        }] + results

                        clip_cache = {}
                        b64_cache = {}
                        with st.spinner(f"🎵 Loading player — buffering {BUFFER_SIZE} tracks..."):
                            prefill_buffer_sync(playlist, clip_cache, b64_cache, tmp_dir, start_from=0)

                        st.session_state["player_active"] = True
                        st.session_state["playlist"] = playlist
                        st.session_state["current_index"] = 0
                        st.session_state["clip_cache"] = clip_cache
                        st.session_state["b64_cache"] = b64_cache
                        st.session_state["player_tmp_dir"] = tmp_dir
                        st.session_state["query_track_name"] = selected
                        st.rerun()

            # ---- Artist Search Mode ----
            else:
                import numpy as np

                @st.cache_data(ttl=120)
                def _compute_artist_centroids():
                    """Compute average CLAP embedding per artist."""
                    conn = trackdb.get_db()
                    all_features = trackdb.get_all_features(conn)
                    conn.close()

                    # Group embeddings by artist
                    artist_tracks = {}  # artist -> list of {vec, track_id, title, url}
                    for t in all_features:
                        vec = build_search_vector(t["feature_data"])
                        if vec is not None and len(vec) == 512:
                            artist = t["artist"]
                            if artist not in artist_tracks:
                                artist_tracks[artist] = []
                            artist_tracks[artist].append({
                                "vec": np.array(vec, dtype=np.float32),
                                "track_id": t["track_id"],
                                "title": t["title"],
                                "url": t["url"],
                            })

                    # Compute centroids
                    centroids = {}
                    for artist, tracks in artist_tracks.items():
                        vecs = np.array([t["vec"] for t in tracks])
                        centroids[artist] = {
                            "centroid": vecs.mean(axis=0),
                            "tracks": tracks,
                            "count": len(tracks),
                        }
                    return centroids

                # Search filter for artists
                artist_query = st.text_input(
                    "🔍 Search artists",
                    placeholder="Type to filter artists...",
                    key="artist_search",
                )

                centroids = _compute_artist_centroids()
                artist_names = sorted(centroids.keys(), key=str.lower)

                if artist_query.strip():
                    q = artist_query.strip().lower()
                    artist_names = [a for a in artist_names if q in a.lower()]

                if not artist_names:
                    st.warning(f"No artists matching **\"{artist_query}\"**")
                else:
                    st.caption(f"{len(artist_names)} artists")

                    selected_artist = st.selectbox(
                        "Pick an artist",
                        options=artist_names,
                        label_visibility="collapsed",
                    )

                    if st.button("🔍 Find Similar Artists", type="primary", use_container_width=True):
                        query_centroid = centroids[selected_artist]["centroid"]
                        query_norm = np.linalg.norm(query_centroid)
                        if query_norm == 0:
                            st.error("Could not compute centroid for this artist.")
                            st.stop()
                        query_normed = query_centroid / query_norm

                        # Compute similarity to all other artists
                        similarities = []
                        for artist, data in centroids.items():
                            if artist == selected_artist:
                                continue
                            c = data["centroid"]
                            c_norm = np.linalg.norm(c)
                            if c_norm == 0:
                                continue
                            sim = float(np.dot(query_normed, c / c_norm))
                            similarities.append((artist, sim, data))

                        similarities.sort(key=lambda x: x[1], reverse=True)
                        top_artists = similarities[:15]

                        if not top_artists:
                            st.warning("No similar artists found!")
                            st.stop()

                        st.markdown(f"### Artists similar to **{selected_artist}**")
                        st.caption(f"Based on {centroids[selected_artist]['count']} indexed tracks")

                         # Find closest track pairs for each similar artist
                        query_centroid_normed = query_normed  # already normalized above

                        for rank, (artist, sim, data) in enumerate(top_artists, 1):
                            match_class = "match-high" if sim >= 0.92 else ("match-mid" if sim >= 0.85 else "match-low")
                            pct = f"{sim:.1%}"

                            with st.expander(f"**#{rank} {artist}** — {pct} similar ({data['count']} tracks)", expanded=(rank <= 3)):
                                # Rank candidate's tracks by similarity to query artist's centroid
                                cand_tracks = data["tracks"]
                                cand_vecs = np.array([t["vec"] for t in cand_tracks])
                                cand_norms = np.linalg.norm(cand_vecs, axis=1, keepdims=True)
                                cand_norms[cand_norms == 0] = 1.0
                                cand_vecs_normed = cand_vecs / cand_norms

                                # Similarity of each candidate track to query artist's average
                                centroid_sims = cand_vecs_normed @ query_centroid_normed
                                sorted_indices = np.argsort(centroid_sims)[::-1]

                                st.markdown(f"**Tracks most similar to {selected_artist}'s vibe:**")
                                for pi, ci in enumerate(sorted_indices[:5], 1):
                                    ct = cand_tracks[int(ci)]
                                    track_sim = float(centroid_sims[int(ci)])
                                    st.markdown(
                                        f"{pi}. **{ct['title']}** — {track_sim:.1%} "
                                        f"· [▶️ Listen]({ct['url']})"
                                    )

                                # Play button — builds playlist from this artist's closest tracks
                                if st.button(f"🎵 Play {artist}'s closest tracks", key=f"play_artist_{rank}",
                                             use_container_width=True):
                                    tmp_dir = tempfile.mkdtemp(prefix="deepkt_player_")

                                    # Sort candidate tracks by similarity to query artist's centroid
                                    play_sorted = np.argsort(centroid_sims)[::-1]

                                    playlist = []
                                    for ci in play_sorted[:20]:
                                        ct = cand_tracks[int(ci)]
                                        playlist.append({
                                            "track_id": ct["track_id"],
                                            "artist": artist,
                                            "title": ct["title"],
                                            "url": ct["url"],
                                            "match_pct": round(float(centroid_sims[int(ci)]) * 100, 1),
                                        })

                                    clip_cache = {}
                                    b64_cache = {}
                                    with st.spinner(f"🎵 Loading player — buffering tracks..."):
                                        prefill_buffer_sync(playlist, clip_cache, b64_cache, tmp_dir, start_from=0)

                                    st.session_state["player_active"] = True
                                    st.session_state["playlist"] = playlist
                                    st.session_state["current_index"] = 0
                                    st.session_state["clip_cache"] = clip_cache
                                    st.session_state["b64_cache"] = b64_cache
                                    st.session_state["player_tmp_dir"] = tmp_dir
                                    st.session_state["query_track_name"] = f"Artists like {selected_artist}"
                                    st.rerun()

    # --- Tab 3: Explore Clusters ---
    with tab_clusters:
        st.markdown("### Discover Sonic Sub-Genres")
        st.markdown("This map is generated by grouping tracks with **KMeans** clustering in the native 512-dimensional latent space, then projecting them down to 2D using **PCA**.")

        if stats.get("INDEXED", 0) == 0:
            st.info("Your library is empty. Add links to `links.txt`, run **Analyze** then **Reindex**.")
        else:
            n_clusters = st.slider("Number of Sub-Genres (Clusters)", min_value=2, max_value=20, value=5)

            df = None
            centroids = []

            if st.button("🗺️ Generate Sub-Genre Map", type="primary"):
                st.session_state["show_clusters_n"] = n_clusters
                
            if st.session_state.get("show_clusters_n"):
                # Use the chosen or saved number of clusters
                n_curr = st.session_state["show_clusters_n"]
                with st.spinner("Crunching vectors..."):
                    from deepkt.clustering import compute_clusters
                    import plotly.express as px
    
                    df, centroids = compute_clusters(n_clusters=n_curr)

            if df is not None and not df.empty:
                # 1. 2D Scatter Plot
                fig = px.scatter(
                    df, x="x", y="y", color="cluster",
                    hover_data={"artist": True, "title": True, "x": False, "y": False, "cluster": False},
                    title=f"Phonk Sub-Genre Map ({n_clusters} clusters)",
                    template="plotly_dark",
                    height=600
                )
                fig.update_traces(marker=dict(size=8, opacity=0.8, line=dict(width=0)))
                # Remove axis numbers (PCA axes are arbitrary anyway)
                fig.update_xaxes(showticklabels=False, title="")
                fig.update_yaxes(showticklabels=False, title="")
                st.plotly_chart(fig, use_container_width=True)

                # 2. Centroid Tracks
                st.markdown("### 🎯 Cluster Deep Dive")
                st.markdown("Explore the core of each sub-genre. These tracks are the **closest to the mathematical center** of their cluster.")
                
                # We can do 2 or 3 columns depending on the number of clusters, but for long
                # expanders a simple vertical list of columns is good. Let's do 2 columns.
                cols = st.columns(2)
                for i, c in enumerate(centroids):
                    with cols[i % 2]:
                        with st.expander(f"**Cluster {c['cluster']}** — {c['size']} tracks", expanded=(i==0)):
                            st.caption("Top 10 closest to center 🎯")
                            for j, track in enumerate(c["top_tracks"]):
                                st.markdown(f"**{j+1}.** {track['artist']} — {track['title']}")
                                if track['url']:
                                    st.markdown(f"[▶️ Listen on SoundCloud]({track['url']})")
                                st.markdown("---")

    # --- Tab 4: Training Lab ---
    with tab_lab:
        st.markdown("### 🏋️ AI Training Lab")
        st.markdown(
            "Help the neural network learn your specific Phonk sub-genres.\n\n"
            "This lab automatically finds tracks that the network currently thinks are **identical** to the Anchor. "
            "Swipe 👍 or 👎 to teach it where the true sub-genre boundary lies."
        )

        if stats.get("INDEXED", 0) == 0:
            st.info("Your library is empty. Add links to `links.txt`, run **Analyze** then **Reindex**.")
        else:
            from deepkt import training_lab
            import queue
            
            if "lab_tmp_dir" not in st.session_state:
                st.session_state["lab_tmp_dir"] = tempfile.mkdtemp(prefix="deepkt_lab_")
            if "lab_batches" not in st.session_state:
                st.session_state["lab_batches"] = []
                
            # Transfer completed batches from the background thread global queue to our local session state
            while not training_lab.LAB_BATCH_QUEUE.empty():
                try:
                    st.session_state["lab_batches"].append(training_lab.LAB_BATCH_QUEUE.get_nowait())
                except queue.Empty:
                    break

            batches = st.session_state["lab_batches"]
            loading = training_lab.LAB_IS_LOADING

            # 1. INITIAL LOAD STATE
            if len(batches) == 0:
                if not loading:
                    fetch_lab_batch_async(st.session_state["lab_tmp_dir"])
                    st.session_state["needs_rerun"] = True 
                else:
                    st.info("⏳ Initializing Lab... (Hunting for hard candidates & pre-buffering audio)")
                    st.session_state["needs_rerun"] = True
            else:
                batch = batches[0]
                candidates = batch["candidates"]
                
                # LOOKAHEAD TRIGGER: Always keep the next batch pre-loading in the background
                if len(batches) < 2 and not loading:
                    fetch_lab_batch_async(st.session_state["lab_tmp_dir"])

                # Render Anchor
                st.markdown("---")
                col_anchor_txt, col_anchor_btn = st.columns([3, 1])
                with col_anchor_txt:
                    st.markdown("##### ⚓ Base Track (Anchor)")
                    anchor = batch["anchor"]
                    st.markdown(f"**{anchor['artist']}** — {anchor['title']}")
                with col_anchor_btn:
                    if st.button("⏭️ Skip Anchor", use_container_width=True, help="Discard this anchor and its candidates without saving any labels"):
                        batches.pop(0)
                        st.rerun()
                if batch["anchor_b64"]:
                    render_audio_player_b64(batch["anchor_b64"], autoplay=False)
                else:
                    st.warning("Audio unavailable.")
                
                # Check for candidates left in current batch
                if len(candidates) > 0:
                    st.markdown("---")
                    st.markdown("##### ⚔️ Does this belong to the exact same sub-genre?")
                    cand_data = candidates[0]
                    track = cand_data["track"]
                    b64 = cand_data["b64"]
                    
                    st.markdown(f"**{track['artist']}** — {track['title']}")
                    if b64:
                        render_audio_player_b64(b64, autoplay=False)
                    else:
                        st.warning("Audio unavailable.")

                    def _handle_lab_rating(rating_val):
                        conn = trackdb.get_db()
                        from deepkt.db import save_training_label
                        save_training_label(conn, anchor["track_id"], track["track_id"], rating_val)
                        conn.close()
                        batch["candidates"].pop(0) # Next track!
                        # Auto-balancing is currently disabled by user request
                        # if len(batch["candidates"]) == 0:
                        #     from deepkt.training_lab import auto_balance_batch
                        #     auto_balance_batch(anchor["track_id"])
                        st.rerun()

                    # The magical swipe buttons
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        if st.button("🟢 Perfect Match", use_container_width=True, type="primary"):
                            _handle_lab_rating(1.0)
                    with col2:
                        if st.button("🟡 Medium Match", use_container_width=True):
                            _handle_lab_rating(0.5)
                    with col3:
                        if st.button("🟠 Medium Negative", use_container_width=True):
                            _handle_lab_rating(-0.5)
                    with col4:
                        if st.button("🔴 Complete Negative", use_container_width=True):
                            _handle_lab_rating(-1.0)
                else:
                    st.success("Current batch complete!")
                    if len(batches) > 1:
                        st.info("The next batch is already downloaded and fully pre-buffered.")
                        if st.button("Load Next Batch", use_container_width=True, type="primary"):
                            batches.pop(0)
                            st.rerun()
                    else:
                        st.info("⏳ Still buffering next batch...")
                        st.session_state["needs_rerun"] = True
# --- Tab 5: Artist Discovery ---
    with tab_discovery:
        st.markdown("### ⭐ New Artist Discovery")
        st.markdown("Vibe-check artists discovered by the crawler and promote them to Seed Artists.")
        
        discovered_artists = _get_discovered_artists()
        
        if not discovered_artists:
            st.info("No new artists to discover! Run the crawler to find more.")
        else:
            # Group into a format for the selectbox
            artist_options = { f"{a['name']} ({a['count']} tracks)": a for a in discovered_artists }
            selected_label = st.selectbox("Select an Artist to Audition:", list(artist_options.keys()))
            selected_artist = artist_options[selected_label]
            
            st.markdown(f"**Profile:** [{selected_artist['profile_url']}]({selected_artist['profile_url']})")
            
            # Action Buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🌟 Promote to Seed Artist", use_container_width=True, type="primary"):
                    with open("discovery_seeds.txt", "a") as f:
                        f.write(f"{selected_artist['profile_url']}\n")
                    st.success(f"Added {selected_artist['name']} to discovery_seeds.txt!")
                    
                    # Clear the cache so the dropdown updates instantly
                    _get_discovered_artists.clear()
                    
                    conn = trackdb.get_db()
                    conn.close()
                    st.rerun()
            with col2:
                if st.button("🗑️ Discard Artist & Purge Tracks", use_container_width=True):
                    aname = selected_artist['name']
                    conn = trackdb.get_db()
                    tracks_to_purge = conn.execute("SELECT id FROM tracks WHERE artist = ?", (aname,)).fetchall()
                    purge_ids = [t[0] for t in tracks_to_purge]
                    
                    # Delete from triplets (ensure candidate matches are wiped too)
                    conn.execute("DELETE FROM training_pairs WHERE anchor_id IN (SELECT id FROM tracks WHERE artist = ?) OR candidate_id IN (SELECT id FROM tracks WHERE artist = ?)", (aname, aname))
                    # Delete from features
                    conn.execute("DELETE FROM track_features WHERE track_id IN (SELECT id FROM tracks WHERE artist = ?)", (aname,))
                    # Delete from metadata
                    conn.execute("DELETE FROM tracks WHERE artist = ?", (aname,))
                    conn.commit()
                    conn.close()
                    
                    if purge_ids:
                        try:
                            from deepkt.indexer import get_collection
                            collection = get_collection()
                            collection.delete(ids=purge_ids)
                        except Exception:
                            pass
                            
                    st.toast(f"🗑️ Purged {len(purge_ids)} tracks by {aname}.")
                    st.rerun()

            st.markdown("---")
            st.markdown(f"#### Auditioning: {selected_artist['name']}")
            
            # We need a stable temporary directory to hold these audition files
            import tempfile
            discovery_tmp = st.session_state.setdefault("discovery_tmp_dir", tempfile.mkdtemp(prefix="deepkt_discovery_"))
            
            conn = trackdb.get_db()
            top_tracks = conn.execute("SELECT * FROM tracks WHERE artist = ? ORDER BY id DESC LIMIT 5", (selected_artist['name'],)).fetchall()
            
            for t in top_tracks:
                st.markdown(f"**{t['title']}**")
                
                audio_path = os.path.join(discovery_tmp, f"{t['id']}.mp3")
                
                # If we haven't downloaded this track's snippet yet, show a button to fetch it
                if not os.path.exists(audio_path):
                    if st.button("⬇️ Fetch Audio", key=f"fetch_{t['id']}"):
                        with st.spinner(f"fetching snippet for {t['title']}..."):
                            try:
                                from deepkt.downloader import download_single
                                res = download_single(t['url'], output_dir=discovery_tmp)
                                if res and "file_path" in res and os.path.exists(res["file_path"]):
                                    import shutil
                                    shutil.move(res["file_path"], audio_path)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Could not load audio: {e}")
                else:
                    import base64
                    with open(audio_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    render_audio_player_b64(b64, autoplay=False)
            
            # Safely close connection if we reached here
            try:
                conn.close()
            except:
                pass

# --- Tab 6: Auto-Curate Artist ---
    with tab_autocurate:
        st.markdown("### 🤖 Auto-Curate Artist")
        st.markdown("Paste a SoundCloud artist profile link. Deepkt will automatically grab their Top 30 and most recent 100 tracks, analyze them, and add them to your library.")
        
        artist_url = st.text_input("SoundCloud Artist URL", placeholder="https://soundcloud.com/lxst_cxntury", key="autocurate_url_input")
        
        if st.button("🚀 Start Auto-Curation", use_container_width=True, type="primary"):
            if not artist_url.strip():
                st.error("Please enter an artist URL.")
            else:
                # Trigger the background process
                st.session_state["autocurate_bg"] = {
                    "artist_url": artist_url.strip(),
                    "fetching": True,
                    "urls": [],
                    "total": 0,
                    "error": None
                }
                st.session_state["autocurate_running"] = True
                
                # Clear any old thread state
                st.session_state.pop("autocurate_thread", None)
                st.rerun()

        # Render progress if running
        if st.session_state.get("autocurate_running"):
            bg = st.session_state.get("autocurate_bg", {})
            is_fetching = bg.get("fetching", False)
            urls = bg.get("urls", [])
            total = bg.get("total", 1)
            err = bg.get("error")
            
            # Check if background thread is running
            if "autocurate_thread" not in st.session_state or not st.session_state["autocurate_thread"].is_alive():
                # We need to start the background pipeline
                import threading
                
                def _pipeline_worker(bg_state):
                    from deepkt.crawler import extract_artist_urls
                    try:
                        extracted = extract_artist_urls(bg_state["artist_url"], num_tracks=130)
                        bg_state["urls"] = extracted
                        bg_state["total"] = len(extracted)
                    except Exception as e:
                        bg_state["error"] = str(e)
                        bg_state["urls"] = []
                        bg_state["total"] = 0
                    
                    # Mark fetching as done so UI updates to pipeline view
                    bg_state["fetching"] = False
                    
                    if bg_state.get("urls"):
                        from deepkt.pipeline import run_pipeline
                        from deepkt.indexer import rebuild_search_index
                        try:
                            run_pipeline(urls=bg_state["urls"], resume=False)
                            rebuild_search_index()
                        except Exception as p_err:
                            bg_state["error"] = f"Pipeline execution crashed: {str(p_err)}"
                
                # Only start if we are supposed to be fetching (i.e. fresh start)
                if is_fetching:
                    t = threading.Thread(target=_pipeline_worker, args=(bg,), daemon=True)
                    t.start()
                    st.session_state["autocurate_thread"] = t
            
            # Setup progress vars
            import time
            
            if is_fetching:
                st.info("🔍 Fetching artist profile and track list... (this usually takes 1-2 minutes)")
                with st.spinner("Scraping SoundCloud..."):
                    st.session_state["needs_rerun"] = True
            elif err:
                st.error(f"Error extracting artist: {err}")
                st.session_state["autocurate_running"] = False
            elif not urls:
                st.warning("No valid tracks could be extracted.")
                st.session_state["autocurate_running"] = False
            else:
                from deepkt.pipeline import get_pipeline_status
                from deepkt import db as trackdb
                
                status = get_pipeline_status()
                
                # Simple check of how many of these specific URLs are INDEXED or FAILED
                conn = trackdb.get_db()
                placeholders = ','.join(['?'] * len(urls))
                if urls:
                    query = f"SELECT status, count(*) FROM tracks WHERE url IN ({placeholders}) GROUP BY status"
                    rows = conn.execute(query, urls).fetchall()
                else:
                    rows = []
                conn.close()
                
                url_stats = {r[0]: r[1] for r in rows}
                indexed = url_stats.get("INDEXED", 0)
                failed = url_stats.get("FAILED", 0)
                downloading = url_stats.get("DOWNLOADING", 0)
                analyzing = url_stats.get("ANALYZING", 0)
                downloaded = url_stats.get("DOWNLOADED", 0)
                discovered = url_stats.get("DISCOVERED", 0)
                
                completed = indexed + failed
                
                st.progress(completed / total if total > 0 else 1.0, text=f"Processing {completed}/{total} tracks...")
                cols = st.columns(4)
                cols[0].metric("Downloading", downloading)
                cols[1].metric("Analyzing", analyzing + downloaded)
                cols[2].metric("Indexed", indexed)
                cols[3].metric("Failed", failed)
                
                if status.get("failed_recent"):
                    st.warning("Recent pipeline failures:")
                    for f in status["failed_recent"][:3]:
                        st.caption(f"{f['id']}: {f['error']}")
                        
                if st.session_state["autocurate_thread"].is_alive():
                    with st.spinner("Pipeline running in background..."):
                        st.session_state["needs_rerun"] = True
                else:
                    st.session_state["autocurate_running"] = False
                    st.success("🎉 Auto-curation complete! The search index has been rebuilt.")
                    
            st.markdown("---")

# ============================================================
# Global Polling Loop (Prevents script abortion before tab render)
# ============================================================
if st.session_state.get("needs_rerun", False):
    st.session_state["needs_rerun"] = False
    import time
    time.sleep(1.5)
    st.rerun()


# --- Footer ---
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:#555; font-size:0.8rem;">'
    'Deepkt · Project by Adrian Partain · Fair Use — all links point to original platforms'
    '</p>',
    unsafe_allow_html=True,
)
