import sqlite3
import json
import numpy as np
import umap
from rich.console import Console
from rich.progress import Progress
from deepkt import db as trackdb
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

console = Console()

def calculate_neighborhood_hit_rate(high_dim, low_dim, k=10):
    """Calculates what % of the k-nearest neighbors in high-dim are preserved in low-dim."""
    nn_high = NearestNeighbors(n_neighbors=k + 1, metric='cosine').fit(high_dim)
    indices_high = nn_high.kneighbors(high_dim, return_distance=False)[:, 1:]

    nn_low = NearestNeighbors(n_neighbors=k + 1, metric='euclidean').fit(low_dim)
    indices_low = nn_low.kneighbors(low_dim, return_distance=False)[:, 1:]

    hits = 0
    for i in range(len(high_dim)):
        intersection = np.intersect1d(indices_high[i], indices_low[i])
        hits += len(intersection)
    
    return hits / (len(high_dim) * k)

def generate_umap_map(n_neighbors=500, min_dist=0.15, spread=2.0, metric='cosine'):
    console.print("\n[bold magenta]🌌 Initializing Global-Structure 2D Map Generation...[/bold magenta]")
    
    # Read raw embeddings from SQLite (not whitened ChromaDB) so PCA can
    # denoise effectively — whitened embeddings amplify noise dimensions
    # which degrades UMAP's nearest-neighbor graph.
    conn = trackdb.get_db()
    rows = conn.execute('''
        SELECT tf.track_id, tf.feature_data
        FROM track_features tf
        JOIN tracks t ON tf.track_id = t.id
        WHERE t.status IN ('DOWNLOADED', 'INDEXED')
    ''').fetchall()
    conn.close()

    track_ids = []
    raw_vectors = []
    for row in rows:
        features = json.loads(row[1])
        embedding = features.get("clap_embedding")
        if embedding and len(embedding) == 512:
            track_ids.append(row[0])
            raw_vectors.append(embedding)

    if not raw_vectors:
        console.print("[red]No embeddings found in database![/red]")
        return

    embeddings = np.array(raw_vectors, dtype=np.float32)
    console.print(f"Loaded {len(embeddings)} raw embeddings from SQLite.")

    # PCA denoising: keep top 30 components that carry broad genre-level
    # distinctions, aggressively discard finer variation that blurs boundaries.
    n_pca = min(30, len(embeddings))
    console.print(f"PCA denoising: 512D → {n_pca}D (keeping genre signal, dropping noise)...")
    pca = PCA(n_components=n_pca, random_state=42)
    pca_embeddings = pca.fit_transform(embeddings)
    explained = pca.explained_variance_ratio_.sum()
    console.print(f"[dim]Retained {explained:.1%} of total variance.[/dim]")

    console.print(f"Running UMAP (Global Structure)...")
    console.print(f"[dim]Parameters: n_neighbors={n_neighbors}, min_dist={min_dist}, spread={spread}, metric={metric}[/dim]")
    
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        spread=spread,
        metric=metric,
        n_components=2,
        random_state=42,
        low_memory=False
    )
    
    projection = reducer.fit_transform(pca_embeddings)
    
    hit_rate = calculate_neighborhood_hit_rate(pca_embeddings, projection, k=10)
    console.print(f"\n[bold yellow]📊 Neighborhood Hit Rate (k=10): {hit_rate:.2%}[/bold yellow]")
    console.print("[dim]This means over 10 neighbors, this % of high-dim neighbors are still neighbors in 2D.[/dim]\n")

    # 4. Save back to SQLite
    console.print("💾 Saving (x, y) coordinates to tracks table...")
    conn = trackdb.get_db()
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Updating database...", total=len(track_ids))
        updates = []
        for i, tid in enumerate(track_ids):
            x, y = float(projection[i, 0]), float(projection[i, 1])
            updates.append((x, y, tid))
            
            if len(updates) >= 500:
                conn.executemany("UPDATE tracks SET x = ?, y = ? WHERE id = ?", updates)
                updates = []
                progress.advance(task, 500)
                
        if updates:
            conn.executemany("UPDATE tracks SET x = ?, y = ? WHERE id = ?", updates)
            progress.advance(task, len(updates))
            
    conn.commit()
    conn.close()
    
    console.print("\n[bold green]✅ Local-Fidelity Map Successfully Generated![/bold green]")

if __name__ == "__main__":
    generate_umap_map()
