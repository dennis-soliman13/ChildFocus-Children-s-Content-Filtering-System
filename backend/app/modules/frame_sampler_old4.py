"""
ChildFocus - Frame Sampling Module
backend/app/modules/frame_sampler.py

Optimizations:
  1. fetch_video()        → validate + download in ONE yt-dlp call (saves ~8-15s)
  2. ThreadPoolExecutor   → S1, S2, S3, thumbnail all run concurrently (saves ~10-20s)
  3. librosa direct read  → no ffmpeg subprocess per segment (saves ~3-6s)
  4. Frame resize 320px   → faster numpy ops on smaller frames
  5. Runtime timer        → printed on completion + returned in response
  6. Short video fix      → segments deduplicated for videos < 20s (e.g. Shorts)
"""

import os
import time
import warnings
import cv2
import numpy as np
import tempfile
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

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

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    print("[ERROR] yt-dlp not installed.")

# ── Constants ──────────────────────────────────────────────────────────────────
SEGMENT_DURATION  = 20
FRAME_SAMPLE_RATE = 1
C_MAX             = 4.0
S_MAX             = 128.0
FRAME_WIDTH       = 320
NODE_PATH         = r"C:\Program Files\nodejs\node.exe"


# ── yt-dlp shared options ──────────────────────────────────────────────────────
def _ydl_opts(extra: dict = None) -> dict:
    opts = {
        "quiet":              True,
        "no_warnings":        True,
        "noprogress":         True,
        "geo_bypass":         True,
        "geo_bypass_country": "US",
        "js_runtimes":        {"node": {"path": NODE_PATH}},
        "remote_components":  ["ejs:github"],
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "web_safari", "android_vr", "tv_embedded"]
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if extra:
        opts.update(extra)
    return opts


# ── Step 0+1 combined: validate AND download in one yt-dlp call ───────────────
def fetch_video(video_id: str, max_duration: int = 90) -> dict:
    """
    Single yt-dlp call — validates availability AND downloads.
    Previous version made two separate calls (validate then download) = wasted ~8-15s.
    """
    if not YTDLP_AVAILABLE:
        return {"ok": False, "reason": "yt-dlp not installed"}

    output_path = tempfile.mktemp(suffix=".mp4")

    urls_to_try = [
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://www.youtube.com/shorts/{video_id}",
    ]

    last_error = None
    for url in urls_to_try:
        try:
            opts = _ydl_opts({
                "format":            "worst[ext=mp4]/worst",
                "outtmpl":           output_path,
                "download_sections": [f"*0-{max_duration}"],
                "postprocessors":    [],
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not os.path.exists(output_path):
                raise FileNotFoundError("Downloaded file missing")

            return {
                "ok":       True,
                "path":     output_path,
                "title":    info.get("title",    "Unknown"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
            }
        except Exception as e:
            last_error = e
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except Exception: pass
            continue

    msg = str(last_error).lower()
    if "not available" in msg:
        reason = "Video is not available in this region or has been removed"
    elif "private" in msg:
        reason = "Video is private"
    elif "age" in msg:
        reason = "Video is age-restricted"
    else:
        reason = str(last_error)
    return {"ok": False, "reason": reason}


# ── Frame extraction (resized for speed) ──────────────────────────────────────
def extract_frames(video_path: str, start_sec: int, duration: int) -> list:
    """1fps frames resized to 320px wide — faster downstream numpy ops."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    end_frame    = int(min((start_sec + duration) * fps, total_frames))
    start_frame  = int(start_sec * fps)
    step         = max(1, int(fps * FRAME_SAMPLE_RATE))

    frames = []
    idx = start_frame
    while idx < end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (FRAME_WIDTH, int(h * FRAME_WIDTH / w)),
                           interpolation=cv2.INTER_LINEAR)
        frames.append(frame)
        idx += step

    cap.release()
    return frames


# ── FCR ───────────────────────────────────────────────────────────────────────
def compute_fcr(frames: list) -> float:
    if len(frames) < 2:
        return 0.0
    cuts = 0
    prev = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    for f in frames[1:]:
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if np.mean(cv2.absdiff(prev, gray)) > 25:
            cuts += 1
        prev = gray
    return round(min(1.0, (cuts / max(len(frames), 1)) / C_MAX), 4)


# ── CSV ───────────────────────────────────────────────────────────────────────
def compute_csv(frames: list) -> float:
    if not frames:
        return 0.0
    sats = [np.mean(cv2.cvtColor(f, cv2.COLOR_BGR2HSV)[:, :, 1]) for f in frames]
    return round(min(1.0, float(np.std(sats)) / S_MAX), 4)


# ── ATT ───────────────────────────────────────────────────────────────────────
def compute_att(video_path: str, start_sec: int, duration: int) -> float:
    """
    Fast path: librosa reads directly from MP4 — no ffmpeg subprocess.
    Fallback: ffmpeg WAV extraction if direct read fails.
    """
    if LIBROSA_AVAILABLE:
        try:
            y, sr = librosa.load(
                video_path,
                offset=float(start_sec),
                duration=float(duration),
                sr=22050,
                mono=True,
            )
            if len(y) > 100:
                return round(min(1.0, float(np.mean(
                    librosa.onset.onset_strength(y=y, sr=sr)
                )) / 10.0), 4)
        except Exception:
            pass

    # Fallback: ffmpeg WAV
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start_sec), "-t", str(duration),
             "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "22050", "-ac", "1", wav_path],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 500:
            if LIBROSA_AVAILABLE:
                y, sr = librosa.load(wav_path, sr=None, mono=True)
                if len(y) > 100:
                    return round(min(1.0, float(np.mean(
                        librosa.onset.onset_strength(y=y, sr=sr)
                    )) / 10.0), 4)
            import wave
            with wave.open(wav_path, "rb") as wf:
                samples = np.frombuffer(
                    wf.readframes(wf.getnframes()), dtype=np.int16
                ).astype(np.float32) / 32768.0
            if len(samples) > 100:
                chunk = 2205
                rms = [float(np.sqrt(np.mean(samples[i:i+chunk]**2)))
                       for i in range(0, len(samples) - chunk, chunk)]
                if rms:
                    return round(min(1.0, float(np.std(rms)) * 10.0), 4)
    except Exception as e:
        print(f"[ATT] Fallback error: {e}")
    finally:
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except Exception: pass
    return 0.0


# ── Thumbnail ─────────────────────────────────────────────────────────────────
def compute_thumbnail_intensity(url: str) -> float:
    if not url:
        return 0.0
    try:
        raw = requests.get(url, timeout=6).content
        img = (cv2.cvtColor(np.array(Image.open(BytesIO(raw)).convert("RGB")),
                            cv2.COLOR_RGB2BGR)
               if PILLOW_AVAILABLE
               else cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR))
        if img is None:
            return 0.0
        mean_sat = float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1])) / 255.0
        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edge_den = float(np.sum(cv2.Canny(gray, 100, 200) > 0)) / float(gray.size)
        return round(min(1.0, 0.7 * mean_sat + 0.3 * edge_den), 4)
    except Exception as e:
        print(f"[THUMB] {e}")
        return 0.0


# ── Process one segment (runs concurrently with other segments) ───────────────
def _process_segment(
    video_path: str, seg_id: str, start: int, seg_dur: int = SEGMENT_DURATION
) -> dict:
    t       = time.time()
    frames  = extract_frames(video_path, start, seg_dur)
    fcr     = compute_fcr(frames)
    csv     = compute_csv(frames)
    att     = compute_att(video_path, start, seg_dur)
    score_h = round(0.35 * fcr + 0.25 * csv + 0.20 * att, 4)
    print(f"[SAMPLER] {seg_id} FCR={fcr} | CSV={csv} | ATT={att} | H={score_h} ({time.time()-t:.1f}s)")
    return {
        "segment_id":     seg_id,
        "offset_seconds": start,
        "length_seconds": seg_dur,
        "fcr": fcr, "csv": csv, "att": att, "score_h": score_h,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def sample_video(video_id: str, thumbnail_url: str = "") -> dict:
    t_start    = time.time()
    video_path = None

    try:
        print(f"\n[SAMPLER] ══════════════════════════════════════")
        print(f"[SAMPLER] Analyzing: {video_id}")

        # Step 1: Fetch (validate + download — one yt-dlp call)
        t0     = time.time()
        result = fetch_video(video_id, max_duration=90)
        print(f"[SAMPLER] Download: {time.time()-t0:.1f}s")

        if not result["ok"]:
            print(f"[SAMPLER] ✗ {result['reason']}")
            return {
                "video_id": video_id, "status": "unavailable",
                "reason":   result["reason"],
                "message":  f"Video cannot be analyzed: {result['reason']}",
            }

        video_path     = result["path"]
        cap            = cv2.VideoCapture(video_path)
        video_duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
        cap.release()
        print(f"[SAMPLER] ✓ '{result['title']}' ({video_duration:.1f}s)")

        # Step 2: Segment starts — short video safe
        actual_dur = min(video_duration, 90)

        if actual_dur <= SEGMENT_DURATION:
            # Video shorter than one segment (e.g. Shorts < 20s)
            effective_seg_dur = max(1, int(actual_dur))
            seg_starts = [
                ("S1", 0),
                ("S2", 0),
                ("S3", 0),
            ]
        else:
            effective_seg_dur = SEGMENT_DURATION
            mid = max(0, int(actual_dur / 2) - effective_seg_dur // 2)
            end = max(0, int(actual_dur) - effective_seg_dur)

            # Deduplicate segment starts
            seen = []
            for v in [0, mid, end]:
                if v not in seen:
                    seen.append(v)
            while len(seen) < 3:
                seen.append(seen[-1])
            seg_starts = list(zip(["S1", "S2", "S3"], seen))

        print(f"[SAMPLER] Segments: {[(s, o) for s, o in seg_starts]} | seg_dur={effective_seg_dur}s")

        # Step 3: All 3 segments + thumbnail concurrently
        t0       = time.time()
        segments = [None, None, None]
        thumb    = 0.0

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_process_segment, video_path, sid, start, effective_seg_dur): i
                for i, (sid, start) in enumerate(seg_starts)
            }
            futures[pool.submit(compute_thumbnail_intensity, thumbnail_url)] = "thumb"

            for future in as_completed(futures):
                key = futures[future]
                if key == "thumb":
                    thumb = future.result()
                    print(f"[SAMPLER] Thumbnail: {thumb}")
                else:
                    segments[key] = future.result()

        print(f"[SAMPLER] Analysis: {time.time()-t0:.1f}s")

        # Step 4: OIR score
        max_seg   = max(s["score_h"] for s in segments)
        agg_score = round(0.80 * max_seg + 0.20 * thumb, 4)
        label     = ("Overstimulating" if agg_score >= 0.75
                     else "Safe"       if agg_score <= 0.35
                     else "Uncertain")

        total = time.time() - t_start
        print(f"[SAMPLER] ✓ Score: {agg_score} → {label}")
        print(f"[SAMPLER] ✓ Total runtime: {total:.1f}s")
        print(f"[SAMPLER] ══════════════════════════════════════\n")

        return {
            "video_id":                  video_id,
            "video_title":               result.get("title", ""),
            "video_duration_sec":        round(video_duration, 1),
            "thumbnail_url":             thumbnail_url,
            "thumbnail_intensity":       thumb,
            "segments":                  segments,
            "aggregate_heuristic_score": agg_score,
            "preliminary_label":         label,
            "status":                    "success",
            "runtime_seconds":           round(total, 2),
        }

    except Exception as e:
        print(f"[SAMPLER] ✗ Fatal: {e}")
        import traceback; traceback.print_exc()
        return {"video_id": video_id, "status": "error", "message": str(e)}
    finally:
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except Exception: pass