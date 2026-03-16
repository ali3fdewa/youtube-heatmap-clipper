"""
heatmap.py — YouTube Most Replayed Heatmap Extraction & Peak Detection

Scrapes the YouTube watch page to extract heatmap (Most Replayed) data,
detects engagement peaks, and generates ranked highlight segments.
"""

import re
import json
import logging
import subprocess
from pathlib import Path
import requests
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
COOKIES_FILE = BASE_DIR / "cookies.txt"


def _ytdlp_base_cmd() -> list[str]:
    """Build the base yt-dlp command with cookies, JS runtime, and EJS flags."""
    cmd = ["yt-dlp"]
    if COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    cmd += ["--js-runtimes", "node"]
    return cmd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_PRE_PAD = 3      # seconds before peak
DEFAULT_POST_PAD = 5     # seconds after peak
DEFAULT_MIN_SEGMENT = 15  # minimum clip length in seconds
DEFAULT_MAX_SEGMENT = 60  # maximum clip length in seconds
DEFAULT_PEAK_THRESHOLD = 0.65  # normalized score threshold


# ---------------------------------------------------------------------------
# Heatmap extraction
# ---------------------------------------------------------------------------
def fetch_watch_page(video_id: str) -> str:
    """Download the raw HTML of a YouTube watch page."""
    url = YOUTUBE_WATCH_URL.format(video_id=video_id)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_heatmap(video_id: str) -> list[dict] | None:
    """
    Extract the Most Replayed heatmap data using multiple strategies.

    Returns a list of dicts: [{\"start\": float, \"intensity\": float}, ...]
    or None if no heatmap data is found.
    """
    # --- Try HTML scraping first (fast, no extra subprocess) ---
    try:
        html = fetch_watch_page(video_id)
    except Exception as e:
        logger.error("Failed to fetch watch page for %s: %s", video_id, e)
        html = None

    if html:
        # --- Strategy 1: heatMarkers JSON array ---
        markers = _extract_heat_markers(html)
        if markers:
            logger.info("Heatmap extracted via heatMarkers array: %d points", len(markers))
            return markers

        # --- Strategy 2: individual heatMarkerRenderer objects ---
        markers = _extract_markers_from_player(html)
        if markers:
            logger.info("Heatmap extracted via individual renderers: %d points", len(markers))
            return markers

        # --- Strategy 3: macroMarkersListEntity (newer format) ---
        markers = _extract_macro_markers(html)
        if markers:
            logger.info("Heatmap extracted via macroMarkersListEntity: %d points", len(markers))
            return markers

    # --- Strategy 4: yt-dlp fallback (slower, runs subprocess) ---
    markers = _extract_via_ytdlp(video_id)
    if markers:
        logger.info("Heatmap extracted via yt-dlp fallback: %d points", len(markers))
        return markers

    logger.warning("No heatmap data found for video %s (tried 4 strategies)", video_id)
    return None


def _extract_via_ytdlp(video_id: str) -> list[dict] | None:
    """Extract heatmap data using yt-dlp's JSON dump (most reliable)."""
    try:
        cmd = _ytdlp_base_cmd() + [
            "--dump-json",
            "--no-download",
            "--no-playlist",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.debug("yt-dlp heatmap extraction failed: %s", result.stderr[:200])
            return None

        info = json.loads(result.stdout)

        # yt-dlp stores heatmap under 'heatmap' key
        heatmap_data = info.get("heatmap")
        if heatmap_data and isinstance(heatmap_data, list):
            markers = []
            for point in heatmap_data:
                if isinstance(point, dict):
                    start = point.get("start_time", point.get("start", 0))
                    end = point.get("end_time", point.get("end", 0))
                    intensity = point.get("value", point.get("intensity", 0))
                    markers.append({"start": float(start), "intensity": float(intensity)})
                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                    markers.append({"start": float(point[0]), "intensity": float(point[1])})
            if markers:
                return markers

        # Also check chapters or markers
        chapters = info.get("chapters") or []
        # Not heatmap data, skip

    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.debug("yt-dlp heatmap extraction error: %s", e)
    except Exception as e:
        logger.debug("yt-dlp heatmap extraction error: %s", e)

    return None


def _extract_heat_markers(html: str) -> list[dict] | None:
    """Parse heatMarkers JSON array from the page source."""
    # Try multiple patterns for the heatMarkers array
    patterns = [
        r'"heatMarkers"\s*:\s*(\[\s*\{.*?\}\s*\])',
        r'heatMarkerDecorationRenderer.*?"heatMarkers"\s*:\s*(\[.*?\])\s*\}',
        r'"decorationMarkersData".*?"heatMarkers"\s*:\s*(\[.*?\])',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            continue

        try:
            raw = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue

        markers = []
        for item in raw:
            renderer = item.get("heatMarkerRenderer", item)
            start_ms = renderer.get("timeRangeStartMillis", 0)
            intensity = renderer.get("heatMarkerIntensityScoreNormalized", 0.0)
            markers.append({
                "start": float(start_ms) / 1000.0 if start_ms > 100 else float(start_ms),
                "intensity": float(intensity),
            })

        if markers:
            return markers

    return None


def _extract_markers_from_player(html: str) -> list[dict] | None:
    """Extract individual heatMarkerRenderer objects from page source."""
    pattern = r'"heatMarkerRenderer"\s*:\s*\{[^}]*?"timeRangeStartMillis"\s*:\s*(\d+)[^}]*?"heatMarkerIntensityScoreNormalized"\s*:\s*([\d.]+)'
    matches = re.finditer(pattern, html)
    markers = []
    for m in matches:
        try:
            start = int(m.group(1)) / 1000.0
            intensity = float(m.group(2))
            markers.append({"start": start, "intensity": intensity})
        except (ValueError, IndexError):
            continue

    # Also try reversed key order
    if not markers:
        pattern2 = r'"heatMarkerIntensityScoreNormalized"\s*:\s*([\d.]+)[^}]*?"timeRangeStartMillis"\s*:\s*(\d+)'
        for m in re.finditer(pattern2, html):
            try:
                intensity = float(m.group(1))
                start = int(m.group(2)) / 1000.0
                markers.append({"start": start, "intensity": intensity})
            except (ValueError, IndexError):
                continue

    return markers if markers else None


def _extract_macro_markers(html: str) -> list[dict] | None:
    """Extract from macroMarkersListEntity (newer YouTube format)."""
    pattern = r'"macroMarkersListEntity"\s*:\s*\{(.*?)"markersList"\s*:\s*\{\s*"markers"\s*:\s*(\[.*?\])'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None

    try:
        raw = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None

    markers = []
    for item in raw:
        start_ms = item.get("startMillis", 0)
        intensity = item.get("intensityScoreNormalized", 0.0)
        if intensity > 0:
            markers.append({
                "start": float(start_ms) / 1000.0,
                "intensity": float(intensity),
            })

    return markers if markers else None


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------
def detect_peaks(
    heatmap: list[dict],
    threshold: float = DEFAULT_PEAK_THRESHOLD,
    min_gap: float = 10.0,
) -> list[dict]:
    """
    Detect peaks in the heatmap data.

    Returns list of {\"time\": float, \"score\": float} sorted by score desc.
    """
    if not heatmap:
        return []

    times = np.array([p["start"] for p in heatmap])
    intensities = np.array([p["intensity"] for p in heatmap])

    # Simple peak detection: find local maxima above threshold
    peaks = []
    for i in range(1, len(intensities) - 1):
        if (
            intensities[i] >= threshold
            and intensities[i] >= intensities[i - 1]
            and intensities[i] >= intensities[i + 1]
        ):
            # Check minimum gap from existing peaks
            t = times[i]
            if all(abs(t - p["time"]) >= min_gap for p in peaks):
                peaks.append({"time": float(t), "score": float(intensities[i])})

    # If no local maxima, take positions above threshold
    if not peaks:
        above = np.where(intensities >= threshold)[0]
        if len(above) > 0:
            # Group contiguous regions
            groups = np.split(above, np.where(np.diff(above) > 1)[0] + 1)
            for group in groups:
                best_idx = group[np.argmax(intensities[group])]
                t = float(times[best_idx])
                if all(abs(t - p["time"]) >= min_gap for p in peaks):
                    peaks.append({"time": t, "score": float(intensities[best_idx])})

    # Sort by score descending
    peaks.sort(key=lambda x: x["score"], reverse=True)
    return peaks


# ---------------------------------------------------------------------------
# Segment generation
# ---------------------------------------------------------------------------
def generate_segments(
    peaks: list[dict],
    duration: float,
    pre_pad: float = DEFAULT_PRE_PAD,
    post_pad: float = DEFAULT_POST_PAD,
    min_length: float = DEFAULT_MIN_SEGMENT,
    max_length: float = DEFAULT_MAX_SEGMENT,
) -> list[dict]:
    """
    Convert detected peaks into clip segments with padding.

    Returns list of {\"start\": float, \"end\": float, \"score\": float}.
    """
    segments = []
    for peak in peaks:
        center = peak["time"]
        half = max(min_length / 2, 10)

        start = max(0, center - half - pre_pad)
        end = min(duration, center + half + post_pad)

        # Enforce max length
        if end - start > max_length:
            mid = (start + end) / 2
            start = max(0, mid - max_length / 2)
            end = min(duration, mid + max_length / 2)

        # Merge with overlapping segments
        merged = False
        for seg in segments:
            if start <= seg["end"] and end >= seg["start"]:
                seg["start"] = min(seg["start"], start)
                seg["end"] = max(seg["end"], end)
                seg["score"] = max(seg["score"], peak["score"])
                merged = True
                break

        if not merged:
            segments.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "score": round(peak["score"], 3),
            })

    # Sort by score desc
    segments.sort(key=lambda x: x["score"], reverse=True)
    return segments


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------
def scan_heatmap(
    video_id: str,
    duration: float,
    pre_pad: float = DEFAULT_PRE_PAD,
    post_pad: float = DEFAULT_POST_PAD,
    threshold: float = DEFAULT_PEAK_THRESHOLD,
) -> dict:
    """
    Full heatmap scan pipeline.

    Returns {\"heatmap\": [...], \"peaks\": [...], \"segments\": [...]}.
    """
    heatmap = extract_heatmap(video_id)
    if not heatmap:
        return {"heatmap": [], "peaks": [], "segments": []}

    peaks = detect_peaks(heatmap, threshold=threshold)
    segments = generate_segments(
        peaks, duration, pre_pad=pre_pad, post_pad=post_pad
    )

    return {
        "heatmap": heatmap,
        "peaks": peaks,
        "segments": segments,
    }
