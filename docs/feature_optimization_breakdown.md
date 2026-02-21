# Phonk Feature Importance Breakdown

Based on the optimization algorithm run across the indexed tracks (to maximize same-artist combinations), some audio features emerged as critical for distinguishing artists, while others proved actively harmful or irrelevant. 

Here is the breakdown of the optimal weights discovered and why they likely matter for this specific genre:

## 🥇 High Importance (Weights > 1.25)

These features are the core "fingerprint" of a Phonk artist's sound. The algorithm heavily prioritized them to separate artists from one another.

### 1. Tempo (Weight: 2.57) - *The Defining Metric*
**Why it's crucial**: Phonk has very strict sub-genres largely defined by BPM (e.g., Drift Phonk at 130-145 BPM vs. aggressive/speed Phonk at 160+ BPM). Artists tend to stick to a specific BPM pocket that defines their groove. Because tempo dictates the entire energy of the track, matching it accurately is the strongest predictor of finding a similar vibe.

### 2. Zero Crossing Rate (Weight: 1.70) - *The Distortion Profile*
**Why it's crucial**: Zero Crossing Rate (ZCR) measures how "noisy" or distorted a signal is. In Phonk, heavy 808 distortion and master-bus clipping are stylistic choices that vary wildly between producers. Some prefer a cleaner, deeper bass (low ZCR), while others push for blown-out, aggressive clipping (high ZCR). This metric perfectly captures that signature "grit."

### 3. RMS Energy (Weight: 1.44) - *The Loudness War*
**Why it's crucial**: RMS measures the sustained perceived loudness of a track. Because Phonk tracks are notoriously over-compressed, the *degree* to which an artist compresses their master bus (how "squashed" vs "dynamic" the mix is) acts as a unique producer signature. 

### 4. Spectral Contrast (Weight: 1.41) - *The Mix Punchiness*
**Why it's crucial**: This measures the difference between peaks (harmonics) and valleys (noise) across frequency bands. It effectively measures how "punchy" or separated the mix is. A producer who uses heavy sidechain compression (making the kick drum punch through the bass) will have a vastly different spectral contrast profile than one who lets the instruments bleed together.

---

## 🥈 Mid Importance (Weights 0.5 - 1.25)

These features are important for general sonic matching but aren't as uniquely tied to a specific artist as the high-importance features.

### 5. Spectral Centroid (Weight: 0.94) - *The Brightness*
**Why it matters**: This measures whether a track is "dark/bassy" (low centroid) or "bright/shimmery" (high centroid). While useful for matching vibes, many Phonk artists release both dark and bright tracks, making it less predictive of the *artist* themselves.

### 6. Onset Strength (Weight: 0.77) - *The Beat Attack*
**Why it matters**: This measures the suddenness of percussive hits. While it helps differentiate between ambient Phonk and aggressive Phonk, the heavy compression used universally in the genre somewhat normalizes this metric across all tracks, making it a weaker differentiator.

### 7. MFCC (Weight: 0.56) - *The General Timbre*
**Why it matters**: MFCCs are traditionally the most important feature for speech recognition and general music genre classification. However, because all Phonk uses very similar instrumentation (cowbells, 808s, Memphis rap vocals), the general timbre is too similar across *all* artists to be a primary differentiator.

---

## ❌ Low Importance / Actively Harmful (Weights < 0.25)

The algorithm actively penalized these features, driving their weights near zero. This means relying on them *hurts* the accuracy of finding similar artists.

### 8. Tonnetz (Weight: 0.16) - *Harmonic Relationships*
**Why it failed**: Tonnetz measures harmonic intervals (like minor thirds or perfect fifths). Phonk is heavily loop-based, often relying on intentionally detuned or atonal Memphis rap samples. Because the harmonic structure is often chaotic or deeply buried under distortion and 808s, measuring intervals yields noisy, unhelpful data.

### 9. Chroma (Weight: 0.01) - *The Musical Key*
**Why it failed (The biggest surprise)**: Chroma measures which specific musical notes (C, D#, G, etc.) are playing. The algorithm almost entirely disabled this feature (weight 0.01). 
**The reason**: If you try to match an aggressive 160 BPM track in C minor with another track purely because it is *also* in C minor, you might end up with a slow, chill track. Musical key has absolutely no correlation with the energy, distortion, or rhythm of a track. Grouping tracks by the notes they use is irrelevant to grouping them by how they *feel*.
