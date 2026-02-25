import sqlite3
import numpy as np

def analyze():
    conn = sqlite3.connect("data/tracks.db")
    c = conn.cursor()
    
    # Grab WARNING
    c.execute('''
        SELECT t.artist, t.title, f.feature_data 
        FROM tracks t 
        JOIN track_features f ON t.id = f.track_id 
        WHERE t.title LIKE '%WARNING%'
    ''')
    warning = c.fetchone()
    if not warning:
        print("Could not find WARNING")
        return
        
    # Grab STARLIGHT
    c.execute('''
        SELECT t.artist, t.title, f.feature_data 
        FROM tracks t 
        JOIN track_features f ON t.id = f.track_id 
        WHERE t.title LIKE '%STARLIGHT%'
    ''')
    starlight = c.fetchone()
    if not starlight:
        print("Could not find STARLIGHT")
        return
        
    print(f"Comparing: {warning[0]} - {warning[1]} vs {starlight[0]} - {starlight[1]}")
    
    import json
    w_data = json.loads(warning[2])
    s_data = json.loads(starlight[2])
    
    print("\n--- Raw Feature Comparison ---")
    features = [
        "tempo", "rms_energy", "hpss_ratio", "tempogram_ratio", 
        "high_freq_percussion", "spectral_contrast_mean", "mid_frequency_flatness"
    ]
    
    for feat in features:
        w_val = w_data[feat][0] if isinstance(w_data[feat], list) else w_data[feat]
        s_val = s_data[feat][0] if isinstance(s_data[feat], list) else s_data[feat]
        
        diff = abs(w_val - s_val)
        print(f"{feat}:")
        print(f"  WARNING:   {w_val:.4f}")
        print(f"  STARLIGHT: {s_val:.4f}")
        print(f"  Diff:      {diff:.4f}")

if __name__ == "__main__":
    analyze()
