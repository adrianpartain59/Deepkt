#!/bin/bash
if [ -f seed/tracks.db.gz ]; then
    mkdir -p data
    echo "Decompressing seed/tracks.db.gz..."
    gunzip -c seed/tracks.db.gz > data/tracks.db
    echo "Done. $(ls -lh data/tracks.db)"
fi

exec python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
