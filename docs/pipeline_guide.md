# Deepkt Pipeline — Visual Guide

## The Big Picture

Every track goes through a linear pipeline that transforms a URL into a searchable point in "Vibe Space."

```mermaid
graph LR
    A["🔗 URL"] -->|yt-dlp| B["🎵 MP3 Snippet\n(30s)"]
    B -->|librosa| C["🧬 DNA Vector\n(16 floats)"]
    C -->|ChromaDB| D["📦 Indexed\n(searchable)"]
    D -->|cosine similarity| E["🎯 Results\n(ranked matches)"]
```

---

## Data Flow — What Happens to a Track

```mermaid
flowchart TD
    subgraph INPUT
        URL["SoundCloud / YouTube URL"]
    end

    subgraph DOWNLOAD["downloader.py"]
        URL --> DL_CHECK{"Duration > 60s?"}
        DL_CHECK -->|Yes| SNIPPET["Download 00:30–01:00"]
        DL_CHECK -->|No| FULL["Download full track"]
        SNIPPET --> MP3["MP3 file (192kbps)"]
        FULL --> MP3
    end

    subgraph ANALYZE["analyzer.py"]
        MP3 --> LOAD["librosa.load()"]
        LOAD --> TRIM["Silence removal\n(trim < -20dB)"]
        TRIM --> FEAT["Extract 4 feature groups"]
        FEAT --> VEC["DNA Vector (16 floats)"]
    end

    subgraph INDEX["indexer.py"]
        VEC --> CHROMA["ChromaDB\n(HNSW cosine index)"]
        META["Artist + Title\n(from filename)"] --> CHROMA
    end

    subgraph QUERY["User searches"]
        QVEC["Query vector"] --> COSINE["Cosine similarity\nsearch"]
        CHROMA --> COSINE
        COSINE --> RESULTS["Ranked matches\nwith % scores"]
    end

    style DOWNLOAD fill:#1a1a2e,stroke:#7c4dff,color:#fff
    style ANALYZE fill:#1a1a2e,stroke:#e040fb,color:#fff
    style INDEX fill:#1a1a2e,stroke:#00e5ff,color:#fff
    style QUERY fill:#1a1a2e,stroke:#00e676,color:#fff
```

---

## The DNA Vector — What's Inside

A single track becomes **16 numbers**. Each number captures a different dimension of the sound:

```
Index   Feature              What it measures                   Example values
─────   ──────────────────   ──────────────────────────────     ──────────────
[0]     BPM                  Energy / speed                     95 – 172
[1-13]  MFCCs (13 values)    Timbre / texture / "grit"          -148 to +137
[14]    Spectral Centroid    Brightness (high=EDM, low=bass)    1200 – 4500
[15]    Zero-Crossing Rate   Noisiness / distortion             0.03 – 0.15
```

```mermaid
graph LR
    subgraph DNA["DNA Vector = [16 floats]"]
        direction LR
        BPM["BPM\n(1)"]
        MFCC["MFCCs\n(13)"]
        BRIGHT["Brightness\n(1)"]
        GRIT["Grit\n(1)"]
    end

    AUDIO["🎵 Audio"] --> BPM
    AUDIO --> MFCC
    AUDIO --> BRIGHT
    AUDIO --> GRIT

    style BPM fill:#7c4dff,color:#fff
    style MFCC fill:#e040fb,color:#fff
    style BRIGHT fill:#00e5ff,color:#000
    style GRIT fill:#ff5252,color:#fff
```

---

## How Similarity Search Works

```mermaid
flowchart LR
    Q["Query vector\n[143, -20, 65, ...]"] --> COS{"Cosine\nSimilarity"}
    
    T1["Track A\n[140, -22, 60, ...]"] --> COS
    T2["Track B\n[95, -76, 108, ...]"] --> COS
    T3["Track C\n[172, -147, 137, ...]"] --> COS
    
    COS --> R1["Track A: 98.5%"]
    COS --> R2["Track B: 82.1%"]
    COS --> R3["Track C: 71.3%"]

    style COS fill:#e040fb,color:#fff
    style R1 fill:#00e5ff,color:#000
```

**Cosine similarity** measures the *angle* between two vectors, ignoring magnitude. Two tracks with the same *proportions* of grit, brightness, and tempo score high — even if one is louder.

---

## File Map — Where Code Lives

```mermaid
graph TD
    subgraph Package["deepkt/"]
        DL["downloader.py\n─────────────\nURL → MP3"]
        AN["analyzer.py\n─────────────\nMP3 → Vector"]
        IX["indexer.py\n─────────────\nVector → ChromaDB\nChromaDB → Results"]
        FB["features/base.py\n─────────────\nExtractor interface"]
    end
    
    subgraph Surfaces["User-facing"]
        APP["app.py\n─────────────\nStreamlit UI"]
        CLI["cli.py\n─────────────\nCommand line"]
    end

    subgraph Config["config/"]
        FY["features.yaml\n─────────────\nDNA Recipe"]
    end

    subgraph Data["data/"]
        RAW["raw_snippets/\n─────────────\nMP3 files"]
        CDB["chroma_db/\n─────────────\nVector index"]
    end

    APP --> DL
    APP --> AN
    APP --> IX
    CLI --> DL
    CLI --> AN
    CLI --> IX
    IX --> AN
    DL --> RAW
    AN --> RAW
    IX --> CDB

    style Package fill:#1a1a2e,stroke:#7c4dff,color:#fff
    style Surfaces fill:#1a1a2e,stroke:#00e5ff,color:#fff
    style Config fill:#1a1a2e,stroke:#e040fb,color:#fff
    style Data fill:#1a1a2e,stroke:#00e676,color:#fff
```

---

## Vibe Sliders — How They Work

The UI vibe sliders don't re-analyze audio. They **modify the query vector** before searching:

```
Original vector:   [143,  -20, ...,  2800,  0.08]
                     ↑BPM              ↑Bright  ↑Grit

Tempo +20:         [163,  -20, ...,  2800,  0.08]   ← shifted BPM
Brightness +30:    [143,  -20, ...,  4300,  0.08]   ← shifted centroid  
Grit +40:          [143,  -20, ...,  2800,  0.28]   ← shifted ZCR
```

This moves the "search point" in Vibe Space without downloading or re-analyzing anything.

---

## Future Pipeline (Phase B+)

```mermaid
flowchart TD
    subgraph Current["✅ Built"]
        URL --> DOWNLOAD --> ANALYZE --> INDEX --> QUERY
    end

    subgraph PhaseB["Phase B: Config-Driven"]
        YAML["features.yaml"] -.-> ANALYZE
        REG["Feature Registry"] -.-> ANALYZE
    end

    subgraph PhaseC["Phase C: Parallel"]
        POOL["Worker Pools"] -.-> DOWNLOAD
        POOL -.-> ANALYZE
        BATCH["Batch Insert"] -.-> INDEX
    end

    subgraph PhaseE["Phase E: Auto-Discovery"]
        CRAWL["Crawler"] -.-> URL
        GATE["Quality Gate"] -.-> INDEX
        DB["SQLite State"] -.-> CRAWL
    end

    style Current fill:#1a1a2e,stroke:#00e676,color:#fff
    style PhaseB fill:#1a1a2e,stroke:#7c4dff,color:#888
    style PhaseC fill:#1a1a2e,stroke:#e040fb,color:#888
    style PhaseE fill:#1a1a2e,stroke:#00e5ff,color:#888
```
