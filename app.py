"""
Deepkt — Streamlit UI for sonic similarity search with integrated music player.
"""

import streamlit as st
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
    .now-playing-dot {
        display: inline-block; width: 8px; height: 8px;
        background: #e040fb; border-radius: 50%;
        animation: pulse 1.5s infinite; margin-right: 8px;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.8); }
    }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
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
        st.markdown(f"""
        <div class="player-card">
            <div class="player-position">
                <span class="now-playing-dot"></span>NOW PLAYING · TRACK {idx + 1} OF {len(playlist)}
            </div>
            <div class="player-track-name">{track['title']}</div>
            <div class="player-track-artist">{track['artist']} · {track['match_pct']}% match</div>
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
    tab_url, tab_library, tab_clusters, tab_lab = st.tabs(["🔗  Search by URL", "📚  Search from Library", "🌌  Explore Clusters", "🏋️  Training Lab"])

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

                with st.spinner("🧬 Extracting Sonic DNA..."):
                    try:
                        feature_dict = analyze_snippet(downloaded_path)
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
                        st.stop()

                # Query for similar tracks (get 20 for a good playlist)
                search_vector = build_search_vector(feature_dict)
                results = query_similar(
                    search_vector,
                    n_results=min(20, track_count),
                )

                if not results:
                    st.warning("No similar tracks found in your library!")
                    st.stop()

                # Build the playlist: query track first, then similar tracks
                playlist = [{
                    "id": "query",
                    "artist": result["artist"],
                    "title": result["title"],
                    "url": url,
                    "match_pct": 100.0,
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
            conn = trackdb.get_db()
            all_features = trackdb.get_all_features(conn)
            conn.close()

            track_options = {
                f"{t['artist']} - {t['title']}": i
                for i, t in enumerate(all_features)
            }
            selected = st.selectbox("Pick a track from your library", list(track_options.keys()))

            if st.button("🔍 Find Similar", type="primary", use_container_width=True):
                idx = track_options[selected]
                track = all_features[idx]

                # Create temp dir for clips
                tmp_dir = tempfile.mkdtemp(prefix="deepkt_player_")

                search_vector = build_search_vector(track["feature_data"])
                results = query_similar(
                    search_vector,
                    n_results=min(20, track_count),
                    exclude_id=track["track_id"],
                )

                if not results:
                    st.warning("No similar tracks found!")
                    st.stop()

                # Build playlist — download the first track's clip to start
                playlist = results
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

    # --- Tab 3: Explore Clusters ---
    with tab_clusters:
        st.markdown("### Discover Sonic Sub-Genres")
        st.markdown("This map is generated by grouping tracks with **KMeans** clustering in the native 512-dimensional latent space, then projecting them down to 2D using **PCA**.")

        if stats.get("INDEXED", 0) == 0:
            st.info("Your library is empty. Add links to `links.txt`, run **Analyze** then **Reindex**.")
        else:
            n_clusters = st.slider("Number of Sub-Genres (Clusters)", min_value=2, max_value=20, value=5)

            with st.spinner("Crunching vectors..."):
                from deepkt.clustering import compute_clusters
                import plotly.express as px

                df, centroids = compute_clusters(n_clusters=n_clusters)

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
                    st.rerun() 
                else:
                    st.info("⏳ Initializing Lab... (Hunting for hard candidates & pre-buffering audio)")
                    import time
                    time.sleep(1) # simple polling loop
                    st.rerun()
            else:
                batch = batches[0]
                candidates = batch["candidates"]
                
                # LOOKAHEAD TRIGGER: If getting close to finishing this batch and next batch isn't queued
                if len(candidates) <= 3 and len(batches) < 2 and not loading:
                    fetch_lab_batch_async(st.session_state["lab_tmp_dir"])

                # Render Anchor
                st.markdown("---")
                st.markdown("##### ⚓ Base Track (Anchor)")
                anchor = batch["anchor"]
                st.markdown(f"**{anchor['artist']}** — {anchor['title']}")
                if batch["anchor_b64"]:
                    render_audio_player_b64(batch["anchor_b64"], autoplay=True)
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

                    # The magical swipe buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("👍 Same Sub-Genre", use_container_width=True, type="primary"):
                            conn = trackdb.get_db()
                            from deepkt.db import save_training_label
                            save_training_label(conn, anchor["track_id"], track["track_id"], 1)
                            conn.close()
                            batch["candidates"].pop(0) # Next track!
                            
                            if len(batch["candidates"]) == 0:
                                from deepkt.training_lab import auto_balance_batch
                                auto_balance_batch(anchor["track_id"])
                                
                            st.rerun()
                    with col2:
                        if st.button("👎 Different Sub-Genre", use_container_width=True):
                            conn = trackdb.get_db()
                            from deepkt.db import save_training_label
                            save_training_label(conn, anchor["track_id"], track["track_id"], 0)
                            conn.close()
                            batch["candidates"].pop(0) # Next track!
                            
                            if len(batch["candidates"]) == 0:
                                from deepkt.training_lab import auto_balance_batch
                                auto_balance_batch(anchor["track_id"])
                                
                            st.rerun()
                else:
                    st.success("Current batch complete!")
                    if len(batches) > 1:
                        st.info("The next batch is already downloaded and fully pre-buffered.")
                        if st.button("Load Next Batch", use_container_width=True, type="primary"):
                            batches.pop(0)
                            st.rerun()
                    else:
                        st.info("⏳ Still buffering next batch...")
                        import time
                        time.sleep(1)
                        st.rerun()

# --- Footer ---
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:#555; font-size:0.8rem;">'
    'Deepkt · Project by Adrian Partain · Fair Use — all links point to original platforms'
    '</p>',
    unsafe_allow_html=True,
)
