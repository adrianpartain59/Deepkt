#!/bin/bash
echo "=== start.sh ==="
echo "PWD: $(pwd)"
echo "seed/ contents: $(ls -la seed/ 2>&1)"
echo "data/ contents: $(ls -la data/ 2>&1)"

if [ ! -f data/tracks.db ] && [ -f seed/tracks.db.gz ]; then
    mkdir -p data
    echo "Decompressing seed/tracks.db.gz..."
    gunzip -c seed/tracks.db.gz > data/tracks.db
    echo "Done. $(ls -lh data/tracks.db)"
else
    echo "Skipped decompression: data/tracks.db exists=$([ -f data/tracks.db ] && echo yes || echo no), seed/tracks.db.gz exists=$([ -f seed/tracks.db.gz ] && echo yes || echo no)"
fi

exec python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
