"""
clipper.py — Video Download & FFmpeg Clip Generation Engine

Downloads YouTube videos once via yt-dlp, generates clips with FFmpeg,
supports parallel processing via ThreadPoolExecutor.
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
CLIPS_DIR = BASE_DIR / "clips"
COOKIES_FILE = BASE_DIR / "cookies.txt"

DOWNLOADS_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)


def _ytdlp_base_cmd() -> list[str]:
    """Build the base yt-dlp command with cookies, JS runtime, and EJS flags."""
    cmd = ["yt-dlp"]
    if COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    cmd += ["--remote-components", "ejs:github"]
    return cmd

# ---------------------------------------------------------------------------
# Aspect ratio presets  (width x height)
# ---------------------------------------------------------------------------
ASPECT_RATIOS = {
    "9:16":     (720, 1280),
    "1:1":      (1080, 1080),
    "16:9":     (1280, 720),
    "original": None,
}


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------
def extract_video_id(url: str) -> str | None:
    """Extract the video ID from various YouTube URL formats."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def get_video_metadata(url: str) -> dict | None:
    """
    Extract video metadata using yt-dlp (no download).

    Returns dict with: video_id, title, channel, duration, thumbnail, url
    """
    try:
        cmd = _ytdlp_base_cmd() + [
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            logger.error("yt-dlp metadata error: %s", result.stderr)
            return None

        info = json.loads(result.stdout)
        return {
            "video_id": info.get("id", ""),
            "title": info.get("title", ""),
            "channel": info.get("channel", info.get("uploader", "")),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "url": url,
        }
    except Exception as e:
        logger.error("Failed to get metadata: %s", e)
        return None


def download_video(url: str, video_id: str | None = None) -> str | None:
    """
    Download video using yt-dlp. Returns the path to the downloaded file.
    Reuses existing download if present.
    """
    if not video_id:
        video_id = extract_video_id(url)
    if not video_id:
        logger.error("Could not extract video ID from URL: %s", url)
        return None

    # Check if already downloaded
    for ext in (".mp4", ".webm", ".mkv"):
        existing = DOWNLOADS_DIR / f"{video_id}{ext}"
        if existing.exists():
            logger.info("Reusing existing download: %s", existing)
            return str(existing)

    output_template = str(DOWNLOADS_DIR / f"{video_id}.%(ext)s")

    try:
        cmd = _ytdlp_base_cmd() + [
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", output_template,
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("yt-dlp download error: %s", result.stderr)
            return None

        # Find the downloaded file
        for ext in (".mp4", ".webm", ".mkv"):
            path = DOWNLOADS_DIR / f"{video_id}{ext}"
            if path.exists():
                return str(path)

        # Fallback: search downloads dir
        for f in DOWNLOADS_DIR.iterdir():
            if f.stem == video_id:
                return str(f)

        return None
    except Exception as e:
        logger.error("Download failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Probe video dimensions
# ---------------------------------------------------------------------------
def get_video_dimensions(input_path: str) -> tuple[int, int]:
    """Get width and height of a video file using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            input_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception:
        return 1920, 1080  # fallback


# ---------------------------------------------------------------------------
# Clip generation
# ---------------------------------------------------------------------------
def generate_clip(
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    aspect_ratio: str = "9:16",
    crop_filter: str | None = None,
    subtitle_path: str | None = None,
) -> dict:
    """
    Generate a single clip using FFmpeg.

    Returns {\"success\": bool, \"output\": str, \"error\": str | None}
    """
    duration = end - start
    out_dims = ASPECT_RATIOS.get(aspect_ratio)

    # Build filter chain
    filters = []

    if crop_filter:
        filters.append(crop_filter)

    if out_dims:
        w, h = out_dims
        filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
        filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")

    if subtitle_path and os.path.exists(subtitle_path):
        # Escape path for FFmpeg (backslashes and colons)
        escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")
        filters.append(f"subtitles='{escaped}'")

    filter_str = ",".join(filters) if filters else None

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
    ]

    if filter_str:
        cmd += ["-vf", filter_str]

    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return {"success": True, "output": output_path, "error": None}
        else:
            logger.error("FFmpeg error: %s", result.stderr[-500:])
            return {"success": False, "output": output_path, "error": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": output_path, "error": "FFmpeg timeout"}
    except Exception as e:
        return {"success": False, "output": output_path, "error": str(e)}


def batch_generate(
    clips_config: list[dict],
    max_workers: int = 3,
    progress_callback=None,
) -> list[dict]:
    """
    Generate multiple clips in parallel using ThreadPoolExecutor.

    clips_config: list of dicts with keys:
        input_path, start, end, output_path, aspect_ratio, crop_filter, subtitle_path

    Returns list of result dicts.
    """
    results = []
    total = len(clips_config)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, cfg in enumerate(clips_config):
            future = executor.submit(
                generate_clip,
                cfg["input_path"],
                cfg["start"],
                cfg["end"],
                cfg["output_path"],
                cfg.get("aspect_ratio", "9:16"),
                cfg.get("crop_filter"),
                cfg.get("subtitle_path"),
            )
            futures[future] = i

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                result["index"] = idx
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "index": idx,
                    "output": clips_config[idx]["output_path"],
                    "error": str(e),
                })

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    results.sort(key=lambda x: x.get("index", 0))
    return results


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def format_timestamp(seconds: float) -> str:
    """Format seconds to HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def list_playlist_videos(playlist_url: str) -> list[dict]:
    """
    List all videos in a YouTube playlist or channel.
    Returns list of {\"url\": str, \"title\": str, \"video_id\": str, \"duration\": float}.
    """
    try:
        cmd = _ytdlp_base_cmd() + [
            "--flat-playlist",
            "--dump-json",
            "--no-download",
            playlist_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return []

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                info = json.loads(line)
                videos.append({
                    "url": f"https://www.youtube.com/watch?v={info.get('id', '')}",
                    "title": info.get("title", ""),
                    "video_id": info.get("id", ""),
                    "duration": info.get("duration", 0) or 0,
                })
            except json.JSONDecodeError:
                continue
        return videos
    except Exception as e:
        logger.error("Playlist listing failed: %s", e)
        return []
