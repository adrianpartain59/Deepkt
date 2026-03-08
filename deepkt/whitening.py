"""
Embedding whitening — mean centering + PCA whitening for improved cosine similarity.

Fitted from the full corpus during reindex and saved to data/whitening_transform.npz.
Applied transparently via build_search_vector(). Raw embeddings in SQLite are never modified.

Why this helps: raw CLAP embeddings share a dominant "average music" direction that
compresses cosine similarity into a narrow band (e.g. 0.70–0.95). Mean centering removes
that shared signal, and PCA whitening equalizes variance across dimensions so no single
axis dominates the similarity computation.
"""

import os
import numpy as np

DEFAULT_TRANSFORM_PATH = "data/whitening_transform.npz"

_cached_transform = None


def fit_and_save(raw_vectors, path=DEFAULT_TRANSFORM_PATH):
    """Fit mean-centering + PCA whitening from the corpus and save to disk.

    Args:
        raw_vectors: List or array of raw embedding vectors (N x D).
        path: File path for the saved transform parameters.

    Returns:
        Dict with 'mean' and 'W' arrays, or None if too few vectors.
    """
    global _cached_transform

    mat = np.array(raw_vectors, dtype=np.float64)

    if mat.shape[0] < 20:
        return None

    mean = mat.mean(axis=0)
    centered = mat - mean

    cov = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # eigh returns ascending order; flip to descending
    eigenvalues = eigenvalues[::-1]
    eigenvectors = eigenvectors[:, ::-1]

    # Scale each principal component by 1/sqrt(eigenvalue).
    # Epsilon prevents amplifying noise from near-zero eigenvalues.
    scale = 1.0 / np.sqrt(np.maximum(eigenvalues, 1e-5))
    W = eigenvectors * scale[np.newaxis, :]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    np.savez(path, mean=mean.astype(np.float32), W=W.astype(np.float32))

    _cached_transform = {"mean": mean.astype(np.float32), "W": W.astype(np.float32)}
    return _cached_transform


def load_transform(path=DEFAULT_TRANSFORM_PATH):
    """Load the saved whitening transform (cached in memory after first load)."""
    global _cached_transform
    if _cached_transform is not None:
        return _cached_transform

    if not os.path.exists(path):
        return None

    data = np.load(path)
    _cached_transform = {"mean": data["mean"], "W": data["W"]}
    return _cached_transform


def apply(raw):
    """Apply whitening to a single vector or matrix.

    Returns the input unchanged if no transform has been fitted.
    Preserves input type: list in → list out, ndarray in → ndarray out.
    """
    transform = load_transform()
    if transform is None:
        return raw

    was_list = isinstance(raw, list)
    arr = np.asarray(raw, dtype=np.float32)
    single = arr.ndim == 1
    if single:
        arr = arr[np.newaxis, :]

    whitened = (arr - transform["mean"]) @ transform["W"]

    if single:
        whitened = whitened[0]
    return whitened.tolist() if was_list else whitened


def clear_cache():
    """Invalidate the in-memory cache (called at the start of reindex)."""
    global _cached_transform
    _cached_transform = None
