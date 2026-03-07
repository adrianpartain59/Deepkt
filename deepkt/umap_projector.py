import sqlite3
import numpy as np
import umap
from rich.console import Console
from rich.progress import Progress
from deepkt.indexer import get_collection
from deepkt import db as trackdb
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

console = Console()

def calculate_neighborhood_hit_rate(high_dim, low_dim, k=10):
    """Calculates what % of the k-nearest neighbors in high-dim are preserved in low-dim."""
    # Find neighbors in 512D (or PCA space)
    nn_high = NearestNeighbors(n_neighbors=k + 1, metric='cosine').fit(high_dim)
    indices_high = nn_high.kneighbors(high_dim, return_distance=False)[:, 1:]

    # Find neighbors in 2D
    nn_low = NearestNeighbors(n_neighbors=k + 1, metric='euclidean').fit(low_dim)
    indices_low = nn_low.kneighbors(low_dim, return_distance=False)[:, 1:]

    hits = 0
    for i in range(len(high_dim)):
        intersection = np.intersect1d(indices_high[i], indices_low[i])
        hits += len(intersection)
    
    return hits / (len(high_dim) * k)

def generate_umap_map(n_neighbors=12, min_dist=0.0, metric='cosine'):
    console.print("\n[bold magenta]🌌 Initializing Local-Fidelity 2D Map Generation...[/bold magenta]")
    
    collection = get_collection()
    count = collection.count()
    data = collection.get(include=["embeddings"])
    
    if not data or len(data.get("embeddings", [])) == 0:
        console.print("[red]No embeddings found in ChromaDB![/red]")
        return
        
    track_ids = data["ids"]
    embeddings = np.array(data["embeddings"])
    
    # 1. High-Component PCA
    # We increase this to 100 to ensure we don't lose the "micro-variance" 
    # that defines local similarity for your music genres.
    n_components = min(100, len(embeddings))
    console.print(f"Reducing dimensions with PCA (512D -> {n_components}D) to preserve local variance...")
    pca = PCA(n_components=n_components, random_state=42)
    pca_embeddings = pca.fit_transform(embeddings)

    # 2. Unsupervised UMAP
    # We REMOVED KMeans/Supervised labels. Labels force global separation 
    # which can pull actual local neighbors apart to fit a cluster 'category'.
    console.print(f"Running UMAP (Focus: Local Neighbors)...")
    console.print(f"[dim]Parameters: n_neighbors={n_neighbors}, min_dist={min_dist}, metric={metric}[/dim]")
    
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,  # Lower = focus on immediate neighbors
        min_dist=min_dist,        # 0.0 = let similar tracks sit right on top of each other
        metric=metric,
        n_components=2,
        random_state=42,
        low_memory=False
    )
    
    projection = reducer.fit_transform(pca_embeddings)
    
    # 3. Validation
    hit_rate = calculate_neighborhood_hit_rate(pca_embeddings, projection, k=10)
    console.print(f"\n[bold yellow]📊 Neighborhood Hit Rate (k=10): {hit_rate:.2%}[/bold yellow]")
    console.print("[dim]This means over 10 neighbors, this % of 512D neighbors are still neighbors in 2D.[/dim]\n")

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
    # Global focus to test overarching sonic structure
    generate_umap_map(n_neighbors=200, min_dist=0.1, metric='cosine')
