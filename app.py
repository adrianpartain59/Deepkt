"""
Deepkt — Streamlit UI for sonic similarity search.
"""

import streamlit as st
import os
import tempfile
import urllib.parse

from deepkt.downloader import smart_download_range
from deepkt.analyzer import analyze_snippet, build_search_vector
from deepkt.indexer import get_collection, rebuild_search_index, query_similar, query_similar_weighted
from deepkt.config import (
    get_enabled_features, get_search_feature_names, get_search_dimensions,
    get_feature_weights, load_feature_config,
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
    .feature-label { font-size: 0.8rem; color: #777; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
    .feature-value { font-size: 1rem; font-weight: 400; color: #ddd; }
    .section-header {
        font-size: 1.3rem; font-weight: 600; color: #e0e0e0;
        margin-top: 2rem; margin-bottom: 0.8rem; padding-bottom: 0.4rem;
        border-bottom: 1px solid var(--border);
    }
    .weight-header {
        font-size: 0.75rem; color: #666; text-transform: uppercase;
        letter-spacing: 1.5px; margin-top: 0.5rem; margin-bottom: -0.3rem;
    }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    hr { border-color: var(--border) !important; }
</style>
""", unsafe_allow_html=True)


# --- Dynamic feature config ---
FEATURE_NAMES = get_search_feature_names()
SEARCH_DIMS = get_search_dimensions()
ENABLED_FEATURES = get_enabled_features()
DEFAULT_WEIGHTS = get_feature_weights()
FEATURE_CONFIG = load_feature_config()

# Human-readable labels and emoji for sidebar sliders
FEATURE_DISPLAY = {
    "tempo":              ("🥁 Tempo (BPM)", "Match tracks with similar tempo"),
    "mfcc":               ("🎨 Timbre / Texture", "The overall 'sound' — grit, warmth, character"),
    "spectral_centroid":  ("✨ Brightness", "Dark/bassy ↔ bright/shimmery"),
    "zero_crossing_rate": ("⚡ Grit / Distortion", "Clean ↔ noisy/distorted"),
    "spectral_contrast":  ("🔨 Punchiness", "How punchy and separated the mix is"),
    "onset_strength":     ("💥 Beat Hardness", "Soft beats ↔ hard-hitting percussion"),
    "rms_energy":         ("📢 Loudness", "Dynamic ↔ compressed/loud"),
    "chroma":             ("🎹 Key / Harmony", "Match tracks with similar musical notes"),
    "tonnetz":            ("🌙 Minor Key Feel", "Harmonic darkness — minor thirds"),
}


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

    # --- Feature Weight Sliders ---
    st.markdown("### 🎚️ Feature Weights")
    st.caption("Control how much each feature influences similarity search. Higher = more influence. 0 = ignore.")

    # Initialize defaults in session state BEFORE widgets render
    for feat_name in ENABLED_FEATURES:
        if f"weight_{feat_name}" not in st.session_state:
            st.session_state[f"weight_{feat_name}"] = DEFAULT_WEIGHTS.get(feat_name, 1.0)

    weights_override = {}
    for feat_name in ENABLED_FEATURES:
        label, tooltip = FEATURE_DISPLAY.get(feat_name, (feat_name, ""))
        w = st.slider(
            label,
            min_value=0.0,
            max_value=3.0,
            step=0.1,
            help=tooltip,
            key=f"weight_{feat_name}",
        )
        weights_override[feat_name] = w

    def _reset_weights():
        for name in ENABLED_FEATURES:
            st.session_state[f"weight_{name}"] = 1.0

    def _zero_weights():
        for name in ENABLED_FEATURES:
            st.session_state[f"weight_{name}"] = 0.0

    col_r, col_z = st.columns(2)
    with col_r:
        st.button("↩️ Reset All", use_container_width=True, on_click=_reset_weights)
    with col_z:
        st.button("🔇 Zero All", use_container_width=True, on_click=_zero_weights)


# ============================================================
# Main Area
# ============================================================
st.markdown('<p class="hero-title">Deepkt</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-subtitle">Find music that sounds like your music — not what an algorithm thinks you should hear.</p>', unsafe_allow_html=True)

tab_url, tab_library = st.tabs(["🔗  Search by URL", "📚  Search from Library"])


def render_results(results, query_name=""):
    if not results:
        st.warning("No similar tracks found. Try adding more songs to your library!")
        return
        
    st.markdown(f'<div class="section-header">🎯 Top Matches{" for " + query_name if query_name else ""}</div>', unsafe_allow_html=True)
    
    # Open DB connection for detailed feature fetching
    conn = trackdb.get_db()
    
    for i, r in enumerate(results):
        pct = r["match_pct"]
        label = f"#{i+1} {r['artist']} — {r['title']} ({pct}% Match)"
        
        with st.expander(label, expanded=False):
            cols = st.columns([3, 1])
            with cols[0]:
                st.caption(f"Match Score: {pct}%")
            with cols[1]:
                if r.get("url"):
                    st.link_button("▶️ Listen", r["url"], help="Open original URL")
                else:
                    # Fallback to SoundCloud search
                    query = f"{r['artist']} {r['title']}"
                    sc_url = f"https://soundcloud.com/search?q={urllib.parse.quote(query)}"
                    st.link_button("🔎 Search SC", sc_url, help="Search on SoundCloud")
            
            # Fetch detailed features for this track
            features = trackdb.get_features(conn, r['id'])
            if features:
                render_feature_breakdown(features, use_expander=False)
            else:
                st.warning("Sonic DNA data unavailable for this track.")
                
    conn.close()


from deepkt.interpreter import SonicInterpreter

@st.cache_resource
def get_interpreter():
    return SonicInterpreter(DEFAULT_DB_PATH)

def render_feature_breakdown(feature_dict, use_expander=True):
    """Show semantic DNA breakdown."""
    interpreter = get_interpreter()
    # If stats aren't loaded (empty DB initially), try loading
    if not interpreter.stats:
        interpreter._load_stats(DEFAULT_DB_PATH)
        
    analysis = interpreter.interpret(feature_dict)
    
    # Helper for content
    def _render_content():
        # 1. Semantic Tags
        if analysis.get("tags"):
            st.markdown('<div style="margin-bottom:1rem;">', unsafe_allow_html=True)
            for tag in analysis["tags"]:
                st.markdown(f'<span class="match-badge match-high" style="margin-right:0.5rem; background:#333; border:1px solid #555;">{tag}</span>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 2a. Tempo Display
        bpm = analysis.get("Tempo", 0)
        if bpm > 0:
            st.markdown(f"**Tempo**: {bpm:.1f} BPM")
            
        # 2b. Vibe Bars
        metrics = [
            ("⚡️ Energy", "Energy"),
            ("💎 Brightness", "Brightness"),
            ("🥊 Punch", "Punch"),
            ("🔪 Edge", "Edge"),
        ]
        
        for label, key in metrics:
            score = analysis.get(key, 0)
            st.write(f"**{label}**")
            st.progress(int(score) / 100)
        
        # 3. Raw Stats Toggle
        if st.checkbox("Show Raw Data", key=f"raw_{id(feature_dict)}"):
            st.json(feature_dict)

    if use_expander:
        with st.expander("🧬 Sonic DNA Breakdown", expanded=False):
            _render_content()
    else:
        st.markdown("##### 🧬 Sonic DNA Breakdown")
        _render_content()




# ============================================================
# Tab 1: Search by URL
# ============================================================
with tab_url:
    url = st.text_input("Paste a SoundCloud or YouTube URL",
        placeholder="https://soundcloud.com/artist/track")

    if st.button("🔍 Analyze & Find Matches", type="primary", use_container_width=True):
        if not url.strip():
            st.error("Please enter a URL.")
        elif track_count == 0:
            st.error("Your library is empty! Add links to `links.txt`, run **Analyze** then **Reindex**.")
        else:
            with st.spinner("⬇️ Downloading snippet..."):
                try:
                    import yt_dlp
                    tmp_dir = tempfile.mkdtemp()
                    ydl_opts = {
                        'format': 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best',
                        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                        'download_ranges': smart_download_range,
                        'force_keyframes_at_cuts': True,
                        'outtmpl': f'{tmp_dir}/%(uploader)s - %(title)s.%(ext)s',
                        'quiet': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        track_name = f"{info.get('uploader', 'Unknown')} - {info.get('title', 'Unknown')}"
                except Exception as e:
                    st.error(f"Download failed: {e}")
                    st.stop()

            mp3_files = [f for f in os.listdir(tmp_dir) if f.endswith(".mp3")]
            if not mp3_files:
                st.error("No audio file was produced. The URL may be invalid.")
                st.stop()

            downloaded_path = os.path.join(tmp_dir, mp3_files[0])

            with st.spinner("🧬 Extracting Sonic DNA..."):
                try:
                    feature_dict = analyze_snippet(downloaded_path)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    st.stop()

            st.success(f"Analyzed: **{track_name}**")
            render_feature_breakdown(feature_dict)
            results = query_similar_weighted(
                feature_dict, weights_override,
                n_results=min(5, track_count),
            )
            render_results(results, query_name=track_name)

            try:
                os.remove(downloaded_path)
                os.rmdir(tmp_dir)
            except:
                pass


# ============================================================
# Tab 2: Search from Library
# ============================================================
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

            render_feature_breakdown(track["feature_data"])

            results = query_similar_weighted(
                track["feature_data"], weights_override,
                n_results=min(5, track_count),
                exclude_id=track["track_id"],
            )
            render_results(results, query_name=selected)


# --- Footer ---
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:#555; font-size:0.8rem;">'
    'Deepkt · Project by Adrian Partain · Fair Use — all links point to original platforms'
    '</p>',
    unsafe_allow_html=True,
)
