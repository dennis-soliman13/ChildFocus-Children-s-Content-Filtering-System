"""
ChildFocus - Data Preprocessing Script
ml_training/scripts/preprocess.py

Steps:
  1. Auto-label rows by query_used (query-based heuristic labeling)
  2. Clean and combine text fields (title + tags + description)
  3. Remove stop words, URLs, special characters
  4. Save labeled + cleaned CSV → data/processed/metadata_clean.csv

Run:
    python preprocess.py
"""

import os
import re
import csv

# ── Paths ──────────────────────────────────────────────────────────────────────
RAW_PATH       = "data/raw/metadata_raw.csv"
PROCESSED_DIR  = "data/processed"
PROCESSED_PATH = "data/processed/metadata_clean.csv"

# ── Query → Label mapping ──────────────────────────────────────────────────────
# Based on collect_metadata.py search queries.
# Overstimulating queries are those known to produce fast-paced/high-stimulus content.
QUERY_LABEL_MAP = {
    "kids fast cartoon compilation":  "Overstimulating",
    "surprise eggs unboxing kids":    "Overstimulating",
    "kids educational videos":        "Educational",
    "kids science experiments":       "Educational",
    "kids yoga and exercise":         "Educational",
    "children cartoon episodes":      "Neutral",
    "nursery rhymes for toddlers":    "Neutral",
    "children's music videos":        "Neutral",
    "animated stories for kids":      "Neutral",
    "baby sensory videos":            "Neutral",
}

# ── Stop words ─────────────────────────────────────────────────────────────────
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "was", "are",
    "be", "as", "so", "we", "he", "she", "they", "you", "i", "my", "your",
    "his", "her", "its", "our", "their", "what", "which", "who", "will",
    "would", "could", "should", "has", "have", "had", "do", "does", "did",
    "not", "no", "if", "then", "than", "when", "where", "how", "all",
    "each", "more", "also", "just", "can", "up", "out", "about", "into",
    "too", "very", "s", "t", "re", "ve", "ll", "d",
}


def assign_label(query: str, existing_label: str) -> str:
    """
    Returns label from existing data if set, else maps from query_used.
    Falls back to 'Neutral' if query not in map.
    """
    if existing_label and existing_label.strip():
        return existing_label.strip()
    query_clean = query.strip().lower()
    return QUERY_LABEL_MAP.get(query_clean, "Neutral")


def clean_text(title: str, description: str) -> str:
    """
    Combine and clean title + description for TF-IDF.
    Title weighted 3x (more signal-dense than description).
    """
    title_part = f"{title} " * 3
    desc_part  = description[:300] if description else ""
    raw        = f"{title_part}{desc_part}".lower()

    # Remove URLs
    raw = re.sub(r"https?://\S+|www\.\S+", " ", raw)
    # Remove non-alpha characters
    raw = re.sub(r"[^a-z\s]", " ", raw)
    # Tokenize + remove stop words
    tokens = [t for t in raw.split() if t not in STOP_WORDS and len(t) > 1]
    return " ".join(tokens)


def preprocess():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    with open(RAW_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"[PREPROCESS] Loaded {len(rows)} rows from {RAW_PATH}")

    processed = []
    label_counts = {"Educational": 0, "Neutral": 0, "Overstimulating": 0, "unknown": 0}

    for row in rows:
        label     = assign_label(row.get("query_used", ""), row.get("label", ""))
        text      = clean_text(row.get("title", ""), row.get("description", ""))

        if not text.strip():
            continue   # skip rows with no usable text

        label_counts[label] = label_counts.get(label, 0) + 1
        processed.append({
            "video_id": row.get("video_id", ""),
            "text":     text,
            "label":    label,
            "title":    row.get("title", ""),
        })

    # Write processed CSV
    with open(PROCESSED_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video_id", "text", "label", "title"])
        writer.writeheader()
        writer.writerows(processed)

    print(f"[PREPROCESS] ✓ {len(processed)} rows saved → {PROCESSED_PATH}")
    print(f"[PREPROCESS] Label distribution:")
    for label, count in label_counts.items():
        if count > 0:
            print(f"             {label}: {count} ({count/len(processed)*100:.1f}%)")


if __name__ == "__main__":
    preprocess()
