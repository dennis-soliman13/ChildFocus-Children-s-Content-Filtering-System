"""
ChildFocus - Naïve Bayes Training Script
ml_training/scripts/train_nb.py

Trains a Complement Naïve Bayes classifier on preprocessed metadata.
ComplementNB handles class imbalance better than MultinomialNB — important
since Overstimulating samples are fewer than Educational/Neutral.

Pipeline:
  1. Load data/processed/metadata_clean.csv
  2. TF-IDF vectorization (unigrams + bigrams, max 5000 features)
  3. 70/30 train/test split (per manuscript: 490 train / 210 test)
  4. Train ComplementNB
  5. Evaluate: Precision, Recall, F1-Score, Confusion Matrix
  6. Save nb_model.pkl + vectorizer.pkl → outputs/

Run:
    python train_nb.py
"""

import os
import csv
import pickle
import random

import numpy as np
from sklearn.naive_bayes import ComplementNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
PROCESSED_PATH  = "data/processed/metadata_clean.csv"
OUTPUTS_DIR     = "../outputs"
MODEL_PATH      = os.path.join(OUTPUTS_DIR, "nb_model.pkl")
VECTORIZER_PATH = os.path.join(OUTPUTS_DIR, "vectorizer.pkl")

# ── Reproducibility ────────────────────────────────────────────────────────────
RANDOM_STATE = 42
random.seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

# ── Label order (must stay consistent with naive_bayes.py) ────────────────────
LABELS = ["Educational", "Neutral", "Overstimulating"]


def load_data(path: str):
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text  = row.get("text", "").strip()
            label = row.get("label", "").strip()
            if text and label in LABELS:
                texts.append(text)
                labels.append(label)
    return texts, labels


def train():
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # ── Load ───────────────────────────────────────────────────────────────────
    print("[TRAIN] Loading processed data...")
    texts, labels = load_data(PROCESSED_PATH)
    print(f"[TRAIN] {len(texts)} samples loaded")

    if len(texts) < 10:
        print("[TRAIN] ✗ Not enough data. Run preprocess.py first.")
        return

    # Label distribution
    for lbl in LABELS:
        count = labels.count(lbl)
        print(f"[TRAIN]   {lbl}: {count} ({count/len(labels)*100:.1f}%)")

    # ── Oversample Overstimulating to balance training data ───────────────────
    # ComplementNB doesn't support class_weight directly.
    # Oversampling minority class makes model more sensitive to catching
    # overstimulating content — critical for a child safety system.
    from sklearn.utils import resample

    neutral_count = labels.count("Neutral")
    texts_over    = [t for t, l in zip(texts, labels) if l == "Overstimulating"]
    labels_over   = [l for l in labels if l == "Overstimulating"]

    if len(texts_over) < neutral_count:
        texts_over_up, labels_over_up = resample(
            texts_over, labels_over,
            n_samples=neutral_count,
            random_state=RANDOM_STATE,
        )
        texts  = texts  + texts_over_up
        labels = labels + labels_over_up
        print(f"[TRAIN] Oversampled Overstimulating: {len(texts_over)} → {neutral_count}")

    # ── Split 70/30 (per manuscript) ───────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels,
        test_size=0.30,
        random_state=RANDOM_STATE,
        stratify=labels,
    )
    print(f"\n[TRAIN] Split: {len(X_train)} train / {len(X_test)} test")

    # ── TF-IDF Vectorization ───────────────────────────────────────────────────
    print("[TRAIN] Fitting TF-IDF vectorizer...")
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),     # unigrams + bigrams
        max_features=5000,      # top 5000 terms
        sublinear_tf=True,      # log(1 + tf) — reduces impact of very frequent terms
        min_df=2,               # ignore terms appearing in only 1 document
        strip_accents="unicode",
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec  = vectorizer.transform(X_test)
    print(f"[TRAIN] Vocabulary size: {len(vectorizer.vocabulary_)}")

    # ── Train ComplementNB ─────────────────────────────────────────────────────
    print("[TRAIN] Training ComplementNB...")
    model = ComplementNB(alpha=0.1)   # alpha=0.1 (lighter smoothing for sparse text)
    model.fit(X_train_vec, y_train)

    # ── Evaluate ───────────────────────────────────────────────────────────────
    print("\n[TRAIN] ══════════════════════════════════════")
    print("[TRAIN] EVALUATION RESULTS")
    print("[TRAIN] ══════════════════════════════════════")

    y_pred = model.predict(X_test_vec)

    # Per-class Precision / Recall / F1
    print("\n[TRAIN] Classification Report:")
    print(classification_report(y_test, y_pred, target_names=LABELS, digits=4))

    # Confusion Matrix
    cm = confusion_matrix(y_test, y_pred, labels=LABELS)
    print("[TRAIN] Confusion Matrix:")
    print(f"{'':>20}", "  ".join(f"{l[:5]:>5}" for l in LABELS))
    for i, row_label in enumerate(LABELS):
        print(f"{row_label:>20}", "  ".join(f"{cm[i][j]:>5}" for j in range(len(LABELS))))

    # Overall metrics
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="weighted"
    )
    accuracy = np.mean(np.array(y_pred) == np.array(y_test))
    print(f"\n[TRAIN] Overall Accuracy : {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"[TRAIN] Weighted Precision: {prec:.4f}")
    print(f"[TRAIN] Weighted Recall   : {rec:.4f}")
    print(f"[TRAIN] Weighted F1-Score : {f1:.4f}")
    print("[TRAIN] ══════════════════════════════════════\n")

    # ── Save model + vectorizer ────────────────────────────────────────────────
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)

    print(f"[TRAIN] ✓ Model saved     → {MODEL_PATH}")
    print(f"[TRAIN] ✓ Vectorizer saved → {VECTORIZER_PATH}")
    print(f"[TRAIN] ✓ Classes: {model.classes_}")
    print(f"[TRAIN] Sprint 2 training complete.")


if __name__ == "__main__":
    train()