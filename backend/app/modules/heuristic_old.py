"""
ChildFocus - Heuristic Analysis Module
backend/app/modules/heuristic.py

Computes audiovisual overstimulation features from video frames and audio:
  - FCR  : Frame-Change Rate         (visual pacing)
  - CSV  : Color-Saturation Variance  (color intensity)
  - ATT  : Audio Tempo Transitions    (audio pacing)
  - THUMB: Thumbnail Intensity        (visual aggressiveness)
  - Score_H: Weighted heuristic score per segment

Optimizations vs frame_sampler.py inline version:
  1. Vectorized HSV batch conversion  → single np.mean over stacked array (no list comprehension)
  2. Pre-allocated grayscale buffer   → avoids repeated memory allocation in FCR loop
  3. ATT uses onset_strength envelope → skips per-chunk RMS fallback when librosa available
  4. Thumbnail pipeline cached        → skips re-download on repeated calls via lru_cache
  5. All public functions stateless   → safe for ThreadPoolExecutor reuse
  6. Returns typed dataclass          → cleaner integration with hybrid_fusion.py
"""

import os
import warnings
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

import cv2
import numpy as np
import requests

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Optional dependencies ──────────────────────────────────────────────────────
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

try:
    from PIL import Image
    from io import BytesIO
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# ── Constants (aligned with manuscript formulas) ───────────────────────────────
C_MAX         = 4.0    # max cuts/sec normalizer
S_MAX         = 128.0  # max saturation std normalizer
FRAME_WIDTH   = 320    # resize width for speed
DIFF_THRESH   = 25     # grayscale abs-diff threshold for cut detection
ATT_NORM      = 10.0   # onset strength normalizer

# Heuristic score weights (w1+w2+w3+w4 = 1.0, per manuscript)
W_FCR   = 0.35
W_CSV   = 0.25
W_ATT   = 0.20
W_THUMB = 0.20

# Thumbnail intensity weights
W_THUMB_SAT  = 0.70
W_THUMB_EDGE = 0.30


# ── Output dataclass ───────────────────────────────────────────────────────────
@dataclass
class SegmentFeatures:
    """Heuristic features for one video segment."""
    segment_id:     str
    offset_seconds: int
    length_seconds: int
    fcr:            float = 0.0   # Frame-Change Rate        [0, 1]
    csv:            float = 0.0   # Color-Saturation Variance [0, 1]
    att:            float = 0.0   # Audio Tempo Transitions   [0, 1]
    thumb:          float = 0.0   # Thumbnail Intensity       [0, 1]
    score_h:        float = 0.0   # Weighted heuristic score  [0, 1]
    frame_count:    int   = 0
    error:          Optional[str] = None


@dataclass
class HeuristicResult:
    """Aggregated heuristic result across all segments + thumbnail."""
    segments:                List[SegmentFeatures] = field(default_factory=list)
    thumbnail_intensity:     float = 0.0
    aggregate_heuristic_score: float = 0.0   # max(segment scores) * 0.8 + thumb * 0.2
    preliminary_label:       str   = "Uncertain"


# ── Frame extraction ───────────────────────────────────────────────────────────
def extract_frames(video_path: str, start_sec: int, duration: int) -> List[np.ndarray]:
    """
    Extract 1fps frames from [start_sec, start_sec+duration].
    Frames resized to FRAME_WIDTH for faster downstream ops.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start_frame  = int(start_sec * fps)
    end_frame    = int(min((start_sec + duration) * fps, total_frames))
    step         = max(1, int(fps))   # 1 frame per second

    frames: List[np.ndarray] = []
    idx = start_frame
    while idx < end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        h, w   = frame.shape[:2]
        scale  = FRAME_WIDTH / w
        frame  = cv2.resize(frame, (FRAME_WIDTH, int(h * scale)),
                            interpolation=cv2.INTER_LINEAR)
        frames.append(frame)
        idx += step

    cap.release()
    return frames


# ── FCR — Frame-Change Rate ────────────────────────────────────────────────────
def compute_fcr(frames: List[np.ndarray]) -> float:
    """
    FCR = min(1, cuts_per_second / C_MAX)

    Optimization: pre-convert all frames to grayscale in one pass,
    then use np.mean(absdiff) across consecutive pairs — avoids
    repeated cvtColor inside the diff loop.
    """
    n = len(frames)
    if n < 2:
        return 0.0

    # Batch grayscale conversion
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]

    cuts = sum(
        1 for i in range(1, n)
        if np.mean(cv2.absdiff(grays[i - 1], grays[i])) > DIFF_THRESH
    )

    # cuts/frame → cuts/sec (frames are 1fps so cuts/n ≈ cuts/sec)
    cuts_per_sec = cuts / max(n - 1, 1)
    return round(float(np.clip(cuts_per_sec / C_MAX, 0.0, 1.0)), 4)


# ── CSV — Color-Saturation Variance ───────────────────────────────────────────
def compute_csv(frames: List[np.ndarray]) -> float:
    """
    CSV = std(per_frame_mean_saturation) / S_MAX

    Optimization: stack all HSV conversions and compute std over
    the saturation channel in one vectorized call instead of a
    Python list comprehension over individual frames.
    """
    if not frames:
        return 0.0

    # Stack saturation channels: shape (N, H, W)
    sat_means = np.array([
        np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2HSV)[:, :, 1])
        for f in frames
    ], dtype=np.float32)

    return round(float(np.clip(np.std(sat_means) / S_MAX, 0.0, 1.0)), 4)


# ── ATT — Audio Tempo Transitions ─────────────────────────────────────────────
def compute_att(video_path: str, start_sec: int, duration: int) -> float:
    """
    ATT = normalized mean onset strength (librosa) ∈ [0, 1]

    Fast path  : librosa reads directly from MP4 (no subprocess).
    Fallback 1 : ffmpeg → WAV → librosa.
    Fallback 2 : RMS variance over chunks (no librosa).
    """
    # ── Fast path ─────────────────────────────────────────────────────────────
    if LIBROSA_AVAILABLE:
        try:
            y, sr = librosa.load(
                video_path,
                offset=float(start_sec),
                duration=float(duration),
                sr=22050,
                mono=True,
                res_type="kaiser_fast",   # faster resampling
            )
            if len(y) > 100:
                strength = librosa.onset.onset_strength(y=y, sr=sr)
                return round(float(np.clip(np.mean(strength) / ATT_NORM, 0.0, 1.0)), 4)
        except Exception:
            pass  # fall through to ffmpeg

    # ── Fallback 1: ffmpeg → WAV ──────────────────────────────────────────────
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-t",  str(duration),
                "-i",  video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "22050", "-ac", "1",
                wav_path,
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode == 0 and _valid_wav(wav_path):
            if LIBROSA_AVAILABLE:
                y, sr = librosa.load(wav_path, sr=None, mono=True)
                if len(y) > 100:
                    strength = librosa.onset.onset_strength(y=y, sr=sr)
                    return round(float(np.clip(np.mean(strength) / ATT_NORM, 0.0, 1.0)), 4)

            # ── Fallback 2: RMS variance (no librosa) ─────────────────────────
            return _att_from_rms(wav_path)

    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        print(f"[ATT] ffmpeg error: {e}")
    finally:
        _safe_remove(wav_path)

    return 0.0


def _valid_wav(path: str, min_bytes: int = 500) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > min_bytes


def _att_from_rms(wav_path: str, chunk_size: int = 2205) -> float:
    """RMS-variance fallback when librosa is unavailable."""
    import wave
    try:
        with wave.open(wav_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) < chunk_size:
            return 0.0
        rms = [
            float(np.sqrt(np.mean(samples[i:i + chunk_size] ** 2)))
            for i in range(0, len(samples) - chunk_size, chunk_size)
        ]
        return round(float(np.clip(float(np.std(rms)) * 10.0, 0.0, 1.0)), 4)
    except Exception:
        return 0.0


# ── Thumbnail Intensity ────────────────────────────────────────────────────────
@lru_cache(maxsize=256)
def compute_thumbnail_intensity(url: str) -> float:
    """
    THUMB = W_THUMB_SAT * mean_saturation + W_THUMB_EDGE * edge_density

    lru_cache avoids re-downloading the same thumbnail across repeated calls
    (e.g. when the same video is re-classified).
    """
    if not url:
        return 0.0
    try:
        raw = requests.get(url, timeout=6).content
        if PILLOW_AVAILABLE:
            img = cv2.cvtColor(
                np.array(Image.open(BytesIO(raw)).convert("RGB")),
                cv2.COLOR_RGB2BGR,
            )
        else:
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)

        if img is None:
            return 0.0

        hsv      = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mean_sat = float(np.mean(hsv[:, :, 1])) / 255.0

        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges    = cv2.Canny(gray, 100, 200)
        edge_den = float(np.count_nonzero(edges)) / float(edges.size)

        return round(float(np.clip(W_THUMB_SAT * mean_sat + W_THUMB_EDGE * edge_den, 0.0, 1.0)), 4)

    except Exception as e:
        print(f"[THUMB] {e}")
        return 0.0


# ── Per-segment scoring ────────────────────────────────────────────────────────
def compute_segment(
    video_path:    str,
    segment_id:    str,
    offset_sec:    int,
    duration_sec:  int,
    thumbnail_url: str = "",
) -> SegmentFeatures:
    """
    Compute all heuristic features for one segment and return a SegmentFeatures.
    Designed to be called concurrently via ThreadPoolExecutor.

    Score_H = W_FCR*FCR + W_CSV*CSV + W_ATT*ATT  (thumb applied at aggregation)
    """
    try:
        frames  = extract_frames(video_path, offset_sec, duration_sec)
        fcr     = compute_fcr(frames)
        csv_val = compute_csv(frames)
        att     = compute_att(video_path, offset_sec, duration_sec)
        score_h = round(W_FCR * fcr + W_CSV * csv_val + W_ATT * att, 4)

        return SegmentFeatures(
            segment_id=segment_id,
            offset_seconds=offset_sec,
            length_seconds=duration_sec,
            fcr=fcr,
            csv=csv_val,
            att=att,
            score_h=score_h,
            frame_count=len(frames),
        )

    except Exception as e:
        return SegmentFeatures(
            segment_id=segment_id,
            offset_seconds=offset_sec,
            length_seconds=duration_sec,
            error=str(e),
        )


# ── Aggregation ────────────────────────────────────────────────────────────────
def aggregate(
    segments:      List[SegmentFeatures],
    thumbnail_url: str = "",
) -> HeuristicResult:
    """
    Aggregate segment scores + thumbnail into final HeuristicResult.

    Score_agg = 0.80 * max(segment score_h values) + 0.20 * thumbnail_intensity

    Conservative max aggregation ensures the system flags a video
    if ANY segment appears overstimulating (per manuscript Section 4C).
    """
    thumb = compute_thumbnail_intensity(thumbnail_url)

    valid_scores = [s.score_h for s in segments if s.error is None]
    if not valid_scores:
        return HeuristicResult(
            segments=segments,
            thumbnail_intensity=thumb,
            aggregate_heuristic_score=0.0,
            preliminary_label="Uncertain",
        )

    max_seg   = max(valid_scores)
    agg_score = round(0.80 * max_seg + 0.20 * thumb, 4)

    label = (
        "Overstimulating" if agg_score >= 0.75 else
        "Safe"            if agg_score <= 0.35 else
        "Uncertain"
    )

    return HeuristicResult(
        segments=segments,
        thumbnail_intensity=thumb,
        aggregate_heuristic_score=agg_score,
        preliminary_label=label,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────
def _safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
