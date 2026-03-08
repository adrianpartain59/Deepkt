"""
Analyzer — Neural Network feature extraction engine.

Extracts semantic audio embeddings using LAION-CLAP Music (trained on music data).
Returns a single 512-dimensional vector that represents the Sonic DNA of the track.
"""

import warnings
import librosa
import numpy as np
import warnings
import numpy as np

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)

# --- Initialize LAION-CLAP Neural Network ---
_processor = None
_model = None
_device = None

def _setup_model():
    """Lazy initialize the neural network on the first call per worker process."""
    global _processor, _model, _device
    if _processor is not None and _model is not None:
        return True

    import torch
    from transformers import ClapModel, ClapProcessor
    _device = "mps" if torch.backends.mps.is_available() else "cpu"
    
    print(f"Loading LAION-CLAP Neural Network to {_device}...")
    try:
        _processor = ClapProcessor.from_pretrained("laion/larger_clap_music")
        _model = ClapModel.from_pretrained("laion/larger_clap_music").to(_device)
        _model.eval()
        return True
    except Exception as e:
        print(f"❌ Failed to load Neural Network: {e}")
        _processor = None
        _model = None
        return False


def analyze_snippet(file_path, config_path=None):
    """Extract a 512-d semantic embedding using LAION-CLAP.

    Args:
        file_path: Path to an audio file (MP3, WAV, etc.)
        config_path: Ignored (legacy parameter).

    Returns:
        Dict: {"clap_embedding": [float, ...]} with 512 dimensions.
    """
    if not _setup_model():
        return {"clap_embedding": [0.0] * 512}

    try:
        import librosa
        import torch
        # 1. Load audio at exactly 48kHz (CLAP requirement)
        y, sr = librosa.load(file_path, sr=48000)

        # 2. Trim silence
        y_trimmed, _ = librosa.effects.trim(y, top_db=20)

        # 3. Process through Neural Network
        inputs = _processor(audio=y_trimmed, sampling_rate=48000, return_tensors="pt").to(_device)
        
        with torch.no_grad():
            outputs = _model.get_audio_features(**inputs)
            
        # Move back to CPU and convert to standard Python float list
        embedding = outputs.pooler_output[0].cpu().numpy().tolist()
        
        # Explicit memory cleanup to prevent MPS memory creep
        del inputs
        del outputs
        if _device == "mps":
            torch.mps.empty_cache()
        
        return {"clap_embedding": embedding}
    except Exception as e:
        print(f"  [WARN] Neural Network analysis failed: {e}")
        return {"clap_embedding": [0.0] * 512}


def build_search_vector(feature_dict, config_path=None, weights_override=None):
    """Extract the embedding for search, with whitening applied if fitted.

    Returns:
        List of floats — the 512-d search vector (whitened if transform exists).
    """
    raw = feature_dict.get("clap_embedding", [0.0] * 512)
    from deepkt.whitening import apply as whiten
    return whiten(raw)


def get_full_feature_names():
    """Return human-readable names for UI (legacy compatibility)."""
    return [f"Semantic Dimension {i+1}" for i in range(512)]

