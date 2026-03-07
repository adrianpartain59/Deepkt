#!/bin/bash
if [ ! -f data/tracks.db ] && [ -f data/tracks.db.gz ]; then
    echo "Decompressing tracks.db.gz..."
    gunzip -k data/tracks.db.gz
    echo "Done. $(ls -lh data/tracks.db)"
fi

exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
