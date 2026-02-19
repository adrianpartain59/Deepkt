"""
Sonic DNA Interpreter
Converts raw feature vectors into human-readable metrics and semantic tags.
"""
import numpy as np
from deepkt import db as trackdb

class SonicInterpreter:
    def __init__(self, db_path=None):
        self.stats = {}
        if db_path:
            self._load_stats(db_path)

    def _load_stats(self, db_path):
        """Calculate min/max for normalization based on library content."""
        conn = trackdb.get_db(db_path)
        tracks = trackdb.get_all_features(conn)
        conn.close()

        if not tracks:
            return

        # Collective arrays for each feature
        collections = {}
        
        for t in tracks:
            for feat, val in t["feature_data"].items():
                if feat not in collections:
                    collections[feat] = []
                # Handle both scalar lists and multi-dim lists
                # We only really care about 1D metrics for simple interpretation
                # For multi-dim (mfcc), maybe take the mean?
                collections[feat].append(val)

        # Calculate semantic ranges
        # logical_features maps internal feature descriptors to "Vibe" names
        self.stats = {}
        
        # 1. Energy (RMS Energy)
        if "rms_energy" in collections:
            vals = [np.mean(v) for v in collections["rms_energy"]]
            self.stats["Energy"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 2. Brightness (Spectral Centroid)
        if "spectral_centroid" in collections:
            vals = [np.mean(v) for v in collections["spectral_centroid"]]
            self.stats["Brightness"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 3. Punch (Onset Strength)
        if "onset_strength" in collections:
            vals = [np.mean(v) for v in collections["onset_strength"]]
            self.stats["Punch"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 4. Rhythm/Complexity (Zero Crossing Rate) -> "Edge"?
        if "zero_crossing_rate" in collections:
            vals = [np.mean(v) for v in collections["zero_crossing_rate"]]
            self.stats["Edge"] = (np.percentile(vals, 5), np.percentile(vals, 95))
            
    def interpret(self, features):
        """Map raw features to 0-100 scores and tags."""
        if not self.stats:
            return {}

        results = {}
        tags = []

        # Helper to normalize
        def normalize(val, bounds):
            min_v, max_v = bounds
            if max_v == min_v: return 50
            norm = (val - min_v) / (max_v - min_v)
            return np.clip(norm * 100, 0, 100)

        # 1. Energy
        if "rms_energy" in features:
            val = np.mean(features["rms_energy"])
            score = normalize(val, self.stats.get("Energy", (0, 1)))
            results["Energy"] = score
            if score > 80: tags.append("⚡️ High Energy")
            elif score < 30: tags.append("🧘 Chill")

        # 2. Brightness
        if "spectral_centroid" in features:
            val = np.mean(features["spectral_centroid"])
            score = normalize(val, self.stats.get("Brightness", (0, 1)))
            results["Brightness"] = score
            if score > 80: tags.append("💎 Crisp")
            elif score < 30: tags.append("🌑 Dark")

        # 3. Punch
        if "onset_strength" in features:
            val = np.mean(features["onset_strength"])
            score = normalize(val, self.stats.get("Punch", (0, 1)))
            results["Punch"] = score
            if score > 80: tags.append("🥊 Punchy")
            elif score < 30: tags.append("☁️ Smooth")

        # 4. Edge (ZCR)
        if "zero_crossing_rate" in features:
            val = np.mean(features["zero_crossing_rate"])
            score = normalize(val, self.stats.get("Edge", (0, 1)))
            results["Edge"] = score
            if score > 80: tags.append("🔪 Sharp")
            elif score < 20: tags.append("🌊 Deep")

        # 5. Tempo (Absolute, not relative)
        if "tempo" in features:
            bpm = features["tempo"][0]
            results["Tempo"] = bpm  # Keep BPM as raw number? Or mapping?
            # Phonk specific tags
            if 120 < bpm < 170: tags.append("🏎️ Phonk Drift")
            elif bpm < 90: tags.append("🐌 Slowed")
            elif bpm > 170: tags.append("🚀 Speed")

        results["tags"] = tags
        return results
