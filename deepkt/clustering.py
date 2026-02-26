import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import euclidean_distances
import streamlit as st

from deepkt import db as trackdb
from deepkt.analyzer import build_search_vector

@st.cache_data(show_spinner=False)
def compute_clusters(n_clusters=5):
    """
    Fetch all indexed tracks, cluster them using KMeans on 512D embeddings,
    reduce to 2D using PCA for visualization, and identify the 'centroid track'
    (best representative) for each cluster.
    """
    conn = trackdb.get_db()
    all_features = trackdb.get_all_features(conn)
    conn.close()

    if not all_features:
        return None, []

    # Prepare data
    track_ids = []
    artists = []
    titles = []
    urls = []
    embeddings = []

    for track in all_features:
        vec = build_search_vector(track["feature_data"])
        if len(vec) == 512:  # Ensure correct dimension
            track_ids.append(track["track_id"])
            artists.append(track["artist"])
            titles.append(track["title"])
            urls.append(track.get("url", ""))
            embeddings.append(vec)

    if not embeddings:
        return None, []

    X = np.array(embeddings)

    # 1. Cluster in 512D space
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X)
    centers = kmeans.cluster_centers_

    # 2. Find the top tracks closest to the center for each cluster
    cluster_details = []
    for k in range(n_clusters):
        # Indices of tracks in this cluster
        cluster_indices = np.where(labels == k)[0]
        if len(cluster_indices) == 0:
            continue
        
        # Get embeddings for this cluster
        cluster_X = X[cluster_indices]
        # Calculate distance to the cluster center
        dists = euclidean_distances(cluster_X, [centers[k]]).flatten()
        
        # Sort indices by distance (ascending)
        sorted_local_indices = np.argsort(dists)
        
        # Take up to top 10
        top_n = min(10, len(sorted_local_indices))
        top_local_indices = sorted_local_indices[:top_n]
        top_global_indices = cluster_indices[top_local_indices]
        top_dists = dists[top_local_indices]
        
        top_tracks = []
        for rank, g_idx in enumerate(top_global_indices):
            top_tracks.append({
                "track_id": track_ids[g_idx],
                "artist": artists[g_idx],
                "title": titles[g_idx],
                "url": urls[g_idx],
                "distance": top_dists[rank]
            })
            
        cluster_details.append({
            "cluster": k,
            "size": len(cluster_indices),
            "top_tracks": top_tracks
        })

    # 3. Reduce to 2D for visualization
    pca = PCA(n_components=2, random_state=42)
    X_2d = pca.fit_transform(X)

    # 4. Build DataFrame for Plotly
    df = pd.DataFrame({
        "track_id": track_ids,
        "artist": artists,
        "title": titles,
        "url": urls,
        "x": X_2d[:, 0],
        "y": X_2d[:, 1],
        "cluster": [f"Cluster {L}" for L in labels],  # String labels for discrete colors
        "cluster_id": labels
    })

    return df, cluster_details
