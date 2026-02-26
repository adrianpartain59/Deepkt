import sqlite3
import os

def import_pairs(file_path, label):
    if not os.path.exists(file_path):
        print(f"Skipping {file_path}, does not exist.")
        return
        
    conn = sqlite3.connect("data/tracks.db")
    cursor = conn.cursor()
    
    success_count = 0
    fail_count = 0
    
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or "|" not in line:
                continue
                
            parts = line.split("|")
            anchor_url = parts[0].strip()
            candidate_url = parts[1].strip()
            
            # Lookup anchor ID
            anchor_row = cursor.execute("SELECT id FROM tracks WHERE url = ?", (anchor_url,)).fetchone()
            if not anchor_row:
                print(f"❌ Anchor URL not found in database: {anchor_url}")
                fail_count += 1
                continue
                
            # Lookup candidate ID
            cand_row = cursor.execute("SELECT id FROM tracks WHERE url = ?", (candidate_url,)).fetchone()
            if not cand_row:
                print(f"❌ Candidate URL not found in database: {candidate_url}")
                fail_count += 1
                continue
                
            a_id = anchor_row[0]
            c_id = cand_row[0]
            
            # Check if pair already exists
            exists = cursor.execute("SELECT 1 FROM training_pairs WHERE anchor_id = ? AND candidate_id = ?", (a_id, c_id)).fetchone()
            if exists:
                print(f"⚠️ Pair already exists: {a_id} -> {c_id}")
                continue
                
            try:
                cursor.execute(
                    "INSERT INTO training_pairs (anchor_id, candidate_id, label) VALUES (?, ?, ?)",
                    (a_id, c_id, label)
                )
                conn.commit()
                success_count += 1
                print(f"✅ Imported {'Positive' if label == 1 else 'Negative'} pair: {a_id} -> {c_id}")
            except sqlite3.Error as e:
                print(f"Database error: {e}")
                fail_count += 1
                
    conn.close()
    print(f"\nCompleted {file_path}: {success_count} inserted, {fail_count} failed.\n")

if __name__ == "__main__":
    print("--- IMPORTING POSITIVE PAIRS ---")
    import_pairs("positive_pairs.txt", label=1)
    
    print("--- IMPORTING NEGATIVE PAIRS ---")
    import_pairs("negative_pairs.txt", label=0)
