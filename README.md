# Deepkt 🧬

**Genre-Agnostic Music Discovery Engine**

Deepkt (formerly SoundDNA) is a specialized application designed to solve the "Cold Start" problem for niche music genres like Phonk, Dark Trap, and Experimental EDM. Instead of relying on metadata or collaborative filtering, it analyzes the raw audio waveform ("Sonic DNA") to find tracks with similar textures, distortion profiles, and rhythmic signatures.

![Deepkt Demo](/assets/interactive_demo.png)

## 🚀 Key Features

-   **Sonic DNA Analysis**: Extracts 43-dimensional feature vectors including Tempo, MFCC (timbre), Chroma (key), Tonnetz (harmony), and Zero-Crossing Rate (edge/distortion).
-   **Phonk-Optimized Tempo Detection**: Custom algorithm to accurately detect high-BPM tracks (130-170 BPM) and handle half-time/double-time matching automatically.
-   **Weighted Similarity Search**: Fine-tune recommendations by adjusting the importance of each audio feature (e.g., prioritize "Rhythm" over "Timbre").
-   **Performance Pipeline**: Multi-threaded downloader and CPU-optimized analyzer capable of processing thousands of tracks.
-   **Interactive UI**: Visualize the "Sonic DNA" of any track with human-readable metrics (Energy, Brightness, Punch, Edge).

## 🛠 Tech Stack

-   **Core**: Python 3.12+
-   **Audio Processing**: Librosa, NumPy
-   **Vector Search**: Scikit-Learn (Euclidean/Cosine with custom weighting)
-   **Database**: SQLite + ChromaDB (planned)
-   **UI**: Streamlit
-   **Extraction**: yt-dlp

## 📦 Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/adrianpartain59/Deepkt.git
    cd Deepkt
    ```

2.  **Set up the environment**
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Install FFmpeg** (Required for audio processing)
    -   macOS: `brew install ffmpeg`
    -   Ubuntu: `sudo apt install ffmpeg`
    -   Windows: Download from ffmpeg.org and add to PATH.

## 🚦 Usage

### 1. Run the Web App
Launch the interactive dashboard to search your library or analyze YouTube/SoundCloud links.
```bash
streamlit run app.py
```

### 2. Build Your Index
Crawled or local audio files are processed via the CLI pipeline.
```bash
# Process a list of URLs
python cli.py pipeline --file links.txt

# Rebuild the search index from the database
python cli.py reindex
```

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.

---

**Project by Adrian Partain**
