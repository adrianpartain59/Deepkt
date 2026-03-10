#!/bin/bash

# Decompress seed database
if [ -f seed/tracks.db.gz ]; then
    mkdir -p data/pipeline
    echo "Decompressing seed/tracks.db.gz..."
    gunzip -c seed/tracks.db.gz > data/tracks.db
    echo "Done. $(ls -lh data/tracks.db)"
fi

# Ensure pipeline directory exists (crawler needs it)
mkdir -p data/pipeline

echo "ffmpeg check: $(which ffmpeg 2>&1 || echo 'NOT FOUND')"

exec python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
