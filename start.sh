#!/bin/bash

# Install ffmpeg if not present (static binary, no package manager needed)
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing static ffmpeg..."
    curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar xJ
    mv ffmpeg-*-static/ffmpeg /usr/local/bin/
    mv ffmpeg-*-static/ffprobe /usr/local/bin/
    rm -rf ffmpeg-*-static
    echo "ffmpeg installed: $(ffmpeg -version | head -1)"
fi

# Decompress seed database
if [ -f seed/tracks.db.gz ]; then
    mkdir -p data
    echo "Decompressing seed/tracks.db.gz..."
    gunzip -c seed/tracks.db.gz > data/tracks.db
    echo "Done. $(ls -lh data/tracks.db)"
fi

exec python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
