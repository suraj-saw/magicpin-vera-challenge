#!/usr/bin/env python3

import os
import sys
import json
from pathlib import Path

# Add dataset folder to path to access generator if needed
WORKSPACE_DIR = Path(__file__).parent.resolve()
DATASET_DIR = WORKSPACE_DIR / "dataset"
EXPANDED_DIR = DATASET_DIR / "expanded"

sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(DATASET_DIR))

from bot import DeterministicComposer

def ensure_dataset_expanded():
    """Ensure the seed dataset is expanded into the full 30 test pairs and json files."""
    test_pairs_file = EXPANDED_DIR / "test_pairs.json"
    if not test_pairs_file.exists():
        print("[Generator] Expanded dataset not found. Expanding seed JSON files now...")
        # pyrefly: ignore [missing-import]
        import generate_dataset
        # Temporarily override sys.argv to run with default flags. 
        # This is a bit hacky but it lets us reuse generate_dataset.py without spawning a heavy subprocess.
        old_argv = sys.argv
        sys.argv = ["generate_dataset.py", "--seed-dir", str(DATASET_DIR), "--out", str(EXPANDED_DIR)]
        try:
            generate_dataset.main()
        finally:
            sys.argv = old_argv
        print("[Generator] Dataset expansion complete.")
    else:
        print("[Generator] Found existing expanded dataset.")

def load_json(path: Path) -> dict:
    # Always force utf-8 here since the dataset has some Hindi text and emojis.
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_submission():
    ensure_dataset_expanded()
    
    test_pairs_file = EXPANDED_DIR / "test_pairs.json"
    pairs_data = load_json(test_pairs_file)
    pairs = pairs_data.get("pairs", [])
    
    if not pairs:
        print("Error: No test pairs found in test_pairs.json!", file=sys.stderr)
        sys.exit(1)
        
    print(f"[Generator] Processing {len(pairs)} test pairs...")
    
    output_lines = []
    stats = {"send_as_vera": 0, "send_as_merchant": 0, "total_chars": 0}
    
    for pair in pairs:
        # Extract the basic identifiers for this test pair
        tid = pair.get("test_id", "T00")
        trig_id = pair.get("trigger_id")
        merch_id = pair.get("merchant_id")
        cust_id = pair.get("customer_id")
        
        # Load the actual context objects from disk using the IDs
        trig = load_json(EXPANDED_DIR / "triggers" / f"{trig_id}.json")
        merch = load_json(EXPANDED_DIR / "merchants" / f"{merch_id}.json")
        
        cust = None
        if cust_id:
            cust_path = EXPANDED_DIR / "customers" / f"{cust_id}.json"
            if cust_path.exists():
                cust = load_json(cust_path)
                
        cat_slug = merch.get("category_slug", "general")
        cat_path = EXPANDED_DIR / "categories" / f"{cat_slug}.json"
        # If the category isn't in the expanded dir, fallback to the base dataset dir.
        # Sometimes categories are static so they don't get copied over during expansion.
        if not cat_path.exists():
            cat_path = DATASET_DIR / "categories" / f"{cat_slug}.json"
        cat = load_json(cat_path) if cat_path.exists() else {}
        
        # Compose message using our 4-context engine
        result = DeterministicComposer.compose(cat, merch, trig, cust)
        
        entry = {
            "test_id": tid,
            "body": result["body"],
            "cta": result["cta"],
            "send_as": result["send_as"],
            "suppression_key": result["suppression_key"],
            "rationale": result["rationale"]
        }
        output_lines.append(json.dumps(entry, ensure_ascii=False))
        
        if result["send_as"] == "vera":
            stats["send_as_vera"] += 1
        else:
            stats["send_as_merchant"] += 1
        stats["total_chars"] += len(result["body"])
        
    # Write everything out to the required jsonl format for the judge
    out_file = WORKSPACE_DIR / "submission.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for line in output_lines:
            f.write(line + "\n")
            
    avg_chars = stats["total_chars"] // len(output_lines) if output_lines else 0
    print(f"\n=======================================================================")
    print(f"  SUCCESS! Generated {len(output_lines)} submission entries in submission.jsonl")
    print(f"  Vera-facing: {stats['send_as_vera']} | Merchant-facing (on behalf): {stats['send_as_merchant']}")
    print(f"  Average message length: {avg_chars} characters")
    print(f"  Output path: {out_file}")
    print(f"=======================================================================\n")

if __name__ == "__main__":
    generate_submission()
