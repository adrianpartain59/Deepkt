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

        # 2. Drum Focus (HPSS Ratio)
        if "hpss_ratio" in collections:
            vals = [np.mean(v) for v in collections["hpss_ratio"]]
            self.stats["Drum Focus"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 3. Timbre (MFCC)
        if "mfcc" in collections:
            vals = [np.mean(v) for v in collections["mfcc"]]
            self.stats["Timbre"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 4. Synth Crushing (Mid Frequency Flatness)
        if "mid_frequency_flatness" in collections:
            vals = [np.mean(v) for v in collections["mid_frequency_flatness"]]
            self.stats["Synth Crushing"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 5. 808 Heaviness (Sub Band Energy)
        if "sub_band_energy" in collections:
            vals = [np.mean(v) for v in collections["sub_band_energy"]]
            self.stats["808 Heaviness"] = (np.percentile(vals, 5), np.percentile(vals, 95))

        # 6. Dynamics (Time Domain Crest)
        if "time_domain_crest" in collections:
            vals = [np.mean(v) for v in collections["time_domain_crest"]]
            self.stats["Dynamics"] = (np.percentile(vals, 5), np.percentile(vals, 95))
            
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

        # 2. Drum Focus
        if "hpss_ratio" in features:
            val = np.mean(features["hpss_ratio"])
            score = normalize(val, self.stats.get("Drum Focus", (0, 1)))
            results["Drum Focus"] = score
            if score > 80: tags.append("🥁 Drum Heavy")
            elif score < 30: tags.append("✨ Atmospheric")

        # 3. Timbre
        if "mfcc" in features:
            val = np.mean(features["mfcc"])
            score = normalize(val, self.stats.get("Timbre", (0, 1)))
            results["Timbre"] = score
            if score > 80: tags.append("🎨 Textured")
            elif score < 30: tags.append("🧊 Clean")

        # 4. Synth Crushing
        if "mid_frequency_flatness" in features:
            val = np.mean(features["mid_frequency_flatness"])
            score = normalize(val, self.stats.get("Synth Crushing", (0, 1)))
            results["Synth Crushing"] = score
            if score > 80: tags.append("📻 Lo-Fi Crushed")
            elif score < 30: tags.append("🎹 Clean Synths")

        # 5. 808 Heaviness
        if "sub_band_energy" in features:
            val = np.mean(features["sub_band_energy"])
            score = normalize(val, self.stats.get("808 Heaviness", (0, 1)))
            results["808 Heaviness"] = score
            if score > 80: tags.append("🔊 Massive 808")
            elif score < 30: tags.append("🌊 Wave Bass")

        # 6. Dynamics
        if "time_domain_crest" in features:
            val = np.mean(features["time_domain_crest"])
            score = normalize(val, self.stats.get("Dynamics", (0, 1)))
            results["Dynamics"] = score
            if score > 80: tags.append("🪩 Bouncy")
            elif score < 30: tags.append("🧱 Slammed (Loud)")

        # 7. Tempo (Absolute, not relative)
        if "tempo" in features:
            bpm = features["tempo"][0]
            results["Tempo"] = bpm
            # Phonk specific tags
            if 120 < bpm < 170: tags.append("🏎️ Phonk Drift")
            elif bpm < 90: tags.append("🐌 Slowed")
            elif bpm > 170: tags.append("🚀 Speed")

        results["tags"] = tags
        return results
