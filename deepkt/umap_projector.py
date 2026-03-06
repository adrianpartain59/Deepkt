import sqlite3
import numpy as np
import umap
from rich.console import Console
from rich.progress import Progress
from deepkt.indexer import get_collection
from deepkt import db as trackdb

console = Console()

def generate_umap_map(n_neighbors=15, min_dist=0.1, metric='cosine'):
    console.print("\n[bold magenta]🌌 Initializing 2D Universe Map Generation...[/bold magenta]")
    
    # Get all vectors from ChromaDB
    collection = get_collection()
    count = collection.count()
    console.print(f"Loading {count} embeddings from database...")
    
    data = collection.get(include=["embeddings"])
    if not data or len(data.get("embeddings", [])) == 0:
        console.print("[red]No embeddings found in ChromaDB![/red]")
        return
        
    track_ids = data["ids"]
    embeddings = np.array(data["embeddings"])
    
    console.print(f"Running UMAP algorithm on {len(embeddings)} tracks (512D -> 2D)...")
    console.print(f"[dim]Parameters: n_neighbors={n_neighbors}, min_dist={min_dist}, metric={metric}[/dim]")
    
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        n_components=2,
        random_state=42 # fixed seed for absolute reproducible map shapes
    )
    
    # Calculate dimensional reduction
    projection = reducer.fit_transform(embeddings)
    
    # Save back to SQLite
    console.print("💾 Saving (x, y) coordinates to tracks table...")
    conn = trackdb.get_db()
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Updating database...", total=len(track_ids))
        
        # Batch updates for massive speedup
        updates = []
        for i, tid in enumerate(track_ids):
            x, y = float(projection[i, 0]), float(projection[i, 1])
            updates.append((x, y, tid))
            
            if len(updates) >= 500:
                conn.executemany("UPDATE tracks SET x = ?, y = ? WHERE id = ?", updates)
                updates = []
                progress.advance(task, 500)
                
        # Final batch
        if updates:
            conn.executemany("UPDATE tracks SET x = ?, y = ? WHERE id = ?", updates)
            progress.advance(task, len(updates))
            
    conn.commit()
    conn.close()
    
    x_min, x_max = np.min(projection[:,0]), np.max(projection[:,0])
    y_min, y_max = np.min(projection[:,1]), np.max(projection[:,1])
    
    console.print("\n[bold green]✅ Universe Map Successfully Generated![/bold green]")
    console.print(f"  X-Axis range: [{x_min:.2f}, {x_max:.2f}]")
    console.print(f"  Y-Axis range: [{y_min:.2f}, {y_max:.2f}]")
    console.print("\n💡 The frontend canvas can now render all points seamlessly.")

if __name__ == "__main__":
    generate_umap_map()
