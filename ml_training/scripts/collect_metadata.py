"""
ChildFocus - Sprint 1 Data Collection
ml_training/scripts/collect_metadata.py

Collects metadata from ~1,050 child-oriented YouTube video IDs.
Balanced across 3 classes (~350 each):
  - Overstimulating : fast-paced, high-stimulus content
  - Educational     : learning-focused content
  - Neutral         : standard child entertainment

Run:
    python collect_metadata.py

Note: YouTube Search API returns max 50 results per call.
      Each query collects up to 50 videos → 21 queries × 50 = ~1,050 total.
"""

import csv
import time
import requests
import os
from dotenv import load_dotenv

load_dotenv("../../backend/.env")
API_KEY = os.getenv("YOUTUBE_API_KEY")

# ── Balanced query list (~350 per class) ──────────────────────────────────────
# 7 queries per class × 50 results = ~350 per class = ~1,050 total
SEARCH_QUERIES = [

    # ── Overstimulating (~350 target) ─────────────────────────────────────────
    # Fast-paced, high-stimulus, sensory-overloading content
    ("kids fast cartoon compilation",    "Overstimulating"),
    ("surprise eggs unboxing kids",      "Overstimulating"),
    ("kids prank videos compilation",    "Overstimulating"),
    ("kids slime videos satisfying",     "Overstimulating"),
    ("kids toy unboxing fast",           "Overstimulating"),
    ("baby shark challenge kids",        "Overstimulating"),
    ("kids gaming loud reaction",        "Overstimulating"),

    # ── Educational (~350 target) ─────────────────────────────────────────────
    # Learning-focused, calm-paced, structured content
    ("kids educational videos",          "Educational"),
    ("kids science experiments",         "Educational"),
    ("kids yoga and exercise",           "Educational"),
    ("preschool learning ABC",           "Educational"),
    ("kids counting numbers learning",   "Educational"),
    ("children learning colors shapes",  "Educational"),
    ("phonics for kids learning",        "Educational"),

    # ── Neutral (~350 target) ─────────────────────────────────────────────────
    # Standard child entertainment — not overstimulating, not explicitly educational
    ("children cartoon episodes",        "Neutral"),
    ("nursery rhymes for toddlers",      "Neutral"),
    ("animated stories for kids",        "Neutral"),
    ("kids bedtime stories",             "Neutral"),
    ("children fairy tales",             "Neutral"),
    ("kids cooking simple recipes",      "Neutral"),
    ("children drawing tutorial",        "Neutral"),
]


def search_youtube(query: str, max_results: int = 50) -> list:
    """Search YouTube Data API v3 for videos matching query."""
    if not API_KEY:
        print("[ERROR] YOUTUBE_API_KEY not set in backend/.env")
        return []

    url    = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part":             "snippet",
        "q":                query,
        "type":             "video",
        "maxResults":       min(max_results, 50),
        "relevanceLanguage": "en",
        "key":              API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] API request failed: {e}")
        return []


def collect_dataset(output_path: str = "data/raw/metadata_raw.csv"):
    os.makedirs("data/raw", exist_ok=True)

    collected  = []
    seen_ids   = set()    # deduplicate video IDs across queries
    label_counts = {"Educational": 0, "Neutral": 0, "Overstimulating": 0}

    total_queries = len(SEARCH_QUERIES)
    for i, (query, label) in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i:02d}/{total_queries}] Searching ({label}): {query}")
        items = search_youtube(query, max_results=50)

        added = 0
        for item in items:
            video_id = item["id"].get("videoId", "")
            if not video_id or video_id in seen_ids:
                continue   # skip duplicates

            seen_ids.add(video_id)
            snippet = item["snippet"]

            collected.append({
                "video_id":   video_id,
                "title":      snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel":    snippet.get("channelTitle", ""),
                "query_used": query,
                "label":      label,    # auto-labeled by query
            })
            label_counts[label] += 1
            added += 1

        print(f"         → {added} new videos (total so far: {len(collected)})")
        time.sleep(1)   # respect API rate limits

    if not collected:
        print("[ERROR] No videos collected. Check your API key.")
        return

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=collected[0].keys())
        writer.writeheader()
        writer.writerows(collected)

    print(f"\n[COLLECT] ══════════════════════════════════════")
    print(f"[COLLECT] ✓ {len(collected)} unique videos saved → {output_path}")
    print(f"[COLLECT] Label distribution:")
    for label, count in label_counts.items():
        pct = count / len(collected) * 100
        print(f"          {label:>20}: {count:>4} ({pct:.1f}%)")
    print(f"[COLLECT] ══════════════════════════════════════")
    print(f"[COLLECT] Next step: python preprocess.py")


if __name__ == "__main__":
    collect_dataset()