"""
ChildFocus - Classification Routes
backend/app/routes/classify.py

Endpoints:
  POST /classify_fast  → Phase 1 (cache) + Phase 2 (NB + thumbnail) ~1-2s
  POST /classify_full  → Phase 3 (full heuristic segmented analysis) ~15s
  GET  /health         → model + DB status check
"""

import sqlite3
import os
import time
from flask import Blueprint, request, jsonify

from app.modules.frame_sampler  import sample_video
from app.modules.youtube_api    import get_video_metadata, extract_video_id, get_thumbnail_url
from app.modules.naive_bayes    import score_from_metadata_dict, model_status

classify_bp = Blueprint("classify", __name__)

# ── DB path ────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(
    os.path.join(_BASE_DIR, "..", "..", "..", "database", "childfocus.db")
)

# ── Thresholds (per manuscript) ────────────────────────────────────────────────
BLOCK_THRESHOLD = 0.75
ALLOW_THRESHOLD = 0.35
NB_WEIGHT       = 0.40    # α
HEURISTIC_WEIGHT = 0.60   # (1 - α)


# ── DB helpers ─────────────────────────────────────────────────────────────────
def _get_cached(video_id: str) -> dict | None:
    """Phase 1 — check DB cache. Returns cached result or None."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB] Cache lookup error: {e}")
        return None


def _save_result(result: dict):
    """Save classification result to DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO videos (
                video_id, video_title, thumbnail_url, thumbnail_intensity,
                heuristic_score, nb_score, final_score, label,
                preliminary_label, classified_by, video_duration_sec,
                runtime_seconds, last_checked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            result.get("video_id"),
            result.get("video_title"),
            result.get("thumbnail_url"),
            result.get("thumbnail_intensity"),
            result.get("heuristic_score"),
            result.get("nb_score"),
            result.get("final_score"),
            result.get("label"),
            result.get("preliminary_label"),
            result.get("classified_by"),
            result.get("video_duration_sec"),
            result.get("runtime_seconds"),
        ))

        # Save segments if present
        if result.get("segments"):
            for seg in result["segments"]:
                if seg:
                    conn.execute("""
                        INSERT INTO segments
                            (video_id, segment_id, offset_seconds, length_seconds,
                             fcr, csv, att, score, frame_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.get("video_id"),
                        seg.get("segment_id"),
                        seg.get("offset_seconds"),
                        seg.get("length_seconds"),
                        seg.get("fcr"),
                        seg.get("csv"),
                        seg.get("att"),
                        seg.get("score_h"),
                        seg.get("frame_count", 0),
                    ))

        conn.commit()
        conn.close()
        print(f"[DB] ✓ Saved result for {result.get('video_id')}")
    except Exception as e:
        print(f"[DB] Save error: {e}")


def _map_label(score: float) -> str:
    """Map score to manuscript label."""
    if score >= BLOCK_THRESHOLD:
        return "Overstimulating"
    elif score <= ALLOW_THRESHOLD:
        return "Educational"
    return "Neutral"


def _action(label: str) -> str:
    """Map label to action per manuscript."""
    return {
        "Overstimulating": "blocked",
        "Neutral":         "blurred",
        "Educational":     "allowed",
    }.get(label, "allowed")


def _log_cache_hit(cached: dict, route: str, runtime: float):
    """Print full classification summary for cache hits."""
    vid   = cached.get("video_id", "?")
    title = (cached.get("video_title") or "")[:45]
    print(f"[CACHE] ══════════════════════════════════════")
    print(f"[CACHE] Hit ({route}): {vid}")
    print(f"[CACHE] Title     : {title!r}")
    print(f"[CACHE] NB Score  : {cached.get('nb_score')}  →  {cached.get('nb_label', 'N/A')}")
    print(f"[CACHE] Heuristic : {cached.get('heuristic_score')}")
    print(f"[CACHE] Thumbnail : {cached.get('thumbnail_intensity')}")
    print(f"[CACHE] Final     : {cached.get('final_score')}  →  {cached.get('label')}  ({cached.get('action')})")
    print(f"[CACHE] Last seen : {cached.get('last_checked')}")
    print(f"[CACHE] Runtime   : {runtime}s")
    print(f"[CACHE] ══════════════════════════════════════")


# ── POST /classify_fast ────────────────────────────────────────────────────────
@classify_bp.route("/classify_fast", methods=["POST"])
def classify_fast():
    """
    Phase 1 + Phase 2 classification.

    Phase 1: DB cache lookup (~100ms) — returns instantly if video seen before.
    Phase 2: NB metadata scoring + thumbnail intensity (~1-2s).

    Decision:
      score ≥ 0.75 → Block immediately
      score ≤ 0.35 → Allow immediately
      else         → Uncertain, recommend /classify_full

    Body: { "video_url": "https://youtube.com/watch?v=..." }
    """
    t_start = time.time()
    data = request.get_json()
    if not data or "video_url" not in data:
        return jsonify({"error": "Missing video_url"}), 400

    video_id = extract_video_id(data["video_url"])
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    # ── Phase 1: Cache lookup ──────────────────────────────────────────────────
    cached = _get_cached(video_id)
    if cached and cached.get("final_score") is not None:
        runtime = round(time.time() - t_start, 3)
        cached["classified_by"] = "cache"
        cached["runtime_seconds"] = runtime
        cached["action"] = _action(cached.get("label", "Neutral"))
        _log_cache_hit(cached, route="classify_fast", runtime=runtime)
        return jsonify(cached)

    # ── Phase 2: Metadata + NB + Thumbnail ────────────────────────────────────
    metadata = get_video_metadata(video_id)
    if "error" in metadata:
        return jsonify({"error": metadata["error"], "video_id": video_id}), 404

    thumbnail_url = metadata.get("thumbnail_url") or get_thumbnail_url(video_id)

    # NB score from metadata
    nb_result  = score_from_metadata_dict(metadata)
    score_nb   = nb_result.score_nb

    # Thumbnail as fast heuristic proxy (no video download)
    from app.modules.frame_sampler import compute_thumbnail_intensity
    thumb_score = compute_thumbnail_intensity(thumbnail_url)

    # Fast fusion: α*NB + (1-α)*thumb
    fast_score    = round(NB_WEIGHT * score_nb + HEURISTIC_WEIGHT * thumb_score, 4)
    label         = _map_label(fast_score)
    action        = _action(label)
    runtime       = round(time.time() - t_start, 3)

    result = {
        "video_id":          video_id,
        "video_title":       metadata.get("title", ""),
        "thumbnail_url":     thumbnail_url,
        "thumbnail_intensity": thumb_score,
        "nb_score":          score_nb,
        "nb_label":          nb_result.predicted_label,
        "nb_confidence":     nb_result.confidence,
        "fast_score":        fast_score,
        "final_score":       fast_score,
        "label":             label,
        "preliminary_label": label,
        "action":            action,
        "classified_by":     "fast_path",
        "runtime_seconds":   runtime,
        "status":            "fast_complete",
        "needs_full_analysis": ALLOW_THRESHOLD < fast_score < BLOCK_THRESHOLD,
    }

    # Save to cache
    _save_result(result)

    print(f"[ROUTE] /classify_fast {video_id} → {label} ({fast_score}) in {runtime}s")
    return jsonify(result)


# ── POST /classify_full ────────────────────────────────────────────────────────
@classify_bp.route("/classify_full", methods=["POST"])
def classify_full():
    """
    Phase 3 — Full heuristic + NB hybrid classification.
    Downloads video, extracts 3 segments, computes FCR/CSV/ATT.
    Then fuses with NB score for final Score_final.

    Body: { "video_url": "...", "thumbnail_url": "..." (optional) }
    """
    t_start = time.time()
    data = request.get_json()
    if not data or "video_url" not in data:
        return jsonify({"error": "Missing video_url"}), 400

    video_id      = extract_video_id(data["video_url"])
    thumbnail_url = data.get("thumbnail_url", "")

    # ── Cache check: only skip if already has heuristic_score ─────────────────
    cached = _get_cached(video_id)
    if cached and cached.get("heuristic_score") is not None:
        runtime = round(time.time() - t_start, 3)
        cached["classified_by"] = "cache"
        cached["runtime_seconds"] = runtime
        cached["action"] = _action(cached.get("label", "Neutral"))
        _log_cache_hit(cached, route="classify_full", runtime=runtime)
        return jsonify(cached)

    # Get thumbnail from API if not provided
    if not thumbnail_url:
        thumbnail_url = get_thumbnail_url(video_id)

    # Run full heuristic analysis (Sprint 1 module)
    heuristic_result = sample_video(video_id, thumbnail_url)

    if heuristic_result.get("status") != "success":
        return jsonify(heuristic_result), 422

    # Get NB score from metadata
    metadata  = get_video_metadata(video_id)
    nb_result = score_from_metadata_dict(metadata) if "error" not in metadata else None
    score_nb  = nb_result.score_nb if nb_result else 0.5
    score_h   = heuristic_result.get("aggregate_heuristic_score", 0.5)

    # Final hybrid fusion: Score_final = α*NB + (1-α)*H
    final_score = round(NB_WEIGHT * score_nb + HEURISTIC_WEIGHT * score_h, 4)
    label       = _map_label(final_score)
    action      = _action(label)
    runtime     = round(time.time() - t_start, 3)

    result = {
        **heuristic_result,
        "nb_score":          score_nb,
        "nb_label":          nb_result.predicted_label if nb_result else "Neutral",
        "heuristic_score":   score_h,
        "final_score":       final_score,
        "label":             label,
        "action":            action,
        "classified_by":     "full_analysis",
        "runtime_seconds":   runtime,
    }

    # Save to cache
    _save_result(result)

    print(f"[ROUTE] /classify_full {video_id} → {label} ({final_score}) in {runtime}s")
    return jsonify(result)


# ── GET /health ────────────────────────────────────────────────────────────────
@classify_bp.route("/health", methods=["GET"])
def health():
    """System health check — model status, DB connectivity."""
    nb_status = model_status()
    db_ok     = False
    try:
        conn  = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        conn.close()
        db_ok = True
    except Exception as e:
        count = 0

    return jsonify({
        "status":        "ok" if nb_status["loaded"] and db_ok else "degraded",
        "nb_model":      nb_status,
        "database":      {"connected": db_ok, "cached_videos": count},
        "db_path":       DB_PATH,
    })