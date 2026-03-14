"""
app.py — AI Viral YouTube Heatmap Clipper

Main Flask application with REST API routes, system checks,
and job management for clip generation.
"""

import os
import sys
import uuid
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory,
)

# Local modules
import heatmap
import clipper
import subtitle
import cropper
import viral_detector
import telegram_bot

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
CLIPS_DIR = BASE_DIR / "clips"
DOWNLOADS_DIR = BASE_DIR / "downloads"
LOGS_DIR = BASE_DIR / "logs"
FONTS_DIR = BASE_DIR / "fonts"

for d in [CLIPS_DIR, DOWNLOADS_DIR, LOGS_DIR, FONTS_DIR]:
    d.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_file = LOGS_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_file)),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

# Job store (in-memory — for production use Redis)
jobs: dict[str, dict] = {}

# ThreadPool for background clip generation
executor = ThreadPoolExecutor(max_workers=3)


# ---------------------------------------------------------------------------
# System checks
# ---------------------------------------------------------------------------
def check_system() -> dict:
    """Verify required system dependencies."""
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "version": sys.version,
            "required": "3.10+",
        },
        "ffmpeg": {"ok": False, "version": "", "required": "any"},
        "yt_dlp": {"ok": False, "version": "", "required": "any"},
    }

    # FFmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            checks["ffmpeg"]["ok"] = True
            checks["ffmpeg"]["version"] = version_line
    except Exception:
        checks["ffmpeg"]["version"] = "Not installed"

    # yt-dlp
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            checks["yt_dlp"]["ok"] = True
            checks["yt_dlp"]["version"] = result.stdout.strip()
    except Exception:
        checks["yt_dlp"]["version"] = "Not installed"

    return checks


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Serve the main dashboard."""
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------
@app.route("/api/system-check", methods=["GET"])
def api_system_check():
    """Return system dependency check results."""
    return jsonify(check_system())


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    Scan a YouTube video: extract metadata, heatmap, and viral scores.

    Body: {\"url\": str, \"threshold\": float, \"pre_pad\": float, \"post_pad\": float}
    """
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Extract metadata
    meta = clipper.get_video_metadata(url)
    if not meta:
        return jsonify({"error": "Failed to extract video metadata. Check the URL."}), 400

    video_id = meta["video_id"]
    duration = meta["duration"]

    # Scan heatmap
    threshold = float(data.get("threshold", 0.65))
    pre_pad = float(data.get("pre_pad", 3))
    post_pad = float(data.get("post_pad", 5))

    heatmap_result = heatmap.scan_heatmap(
        video_id, duration,
        pre_pad=pre_pad,
        post_pad=post_pad,
        threshold=threshold,
    )

    # If we have segments, try to get transcript for viral scoring
    segments = heatmap_result.get("segments", [])

    # Try to get transcript for viral scoring
    transcript_segments = []
    try:
        # Quick transcription using tiny model for viral analysis
        video_path = None
        for ext in (".mp4", ".webm", ".mkv"):
            p = DOWNLOADS_DIR / f"{video_id}{ext}"
            if p.exists():
                video_path = str(p)
                break

        if video_path:
            audio_path = subtitle.extract_audio(video_path)
            if audio_path:
                transcript_segments = subtitle.transcribe(audio_path, model_size="tiny")
    except Exception as e:
        logger.warning("Transcript analysis skipped: %s", e)

    # Compute viral scores
    if transcript_segments and segments:
        segments = viral_detector.analyze_transcript_for_segments(
            transcript_segments, segments
        )
    else:
        # Without transcript, viral_score = heatmap_score
        for seg in segments:
            seg["transcript_score"] = 0.0
            seg["viral_score"] = seg["score"]
            seg["triggers"] = {}

    return jsonify({
        "metadata": meta,
        "heatmap": heatmap_result.get("heatmap", []),
        "segments": segments,
    })


@app.route("/api/clips", methods=["POST"])
def api_create_clips():
    """
    Generate clips from selected segments.

    Body: {
        \"url\": str,
        \"video_id\": str,
        \"segments\": [{\"start\": float, \"end\": float}],
        \"aspect_ratio\": str,
        \"crop_mode\": str,
        \"subtitles\": {\"enabled\": bool, \"model\": str, \"language\": str, \"font\": str, \"position\": str},
    }
    """
    data = request.get_json(force=True)
    url = data.get("url", "")
    video_id = data.get("video_id", "")
    segments = data.get("segments", [])
    aspect_ratio = data.get("aspect_ratio", "9:16")
    crop_mode = data.get("crop_mode", "center")
    sub_config = data.get("subtitles", {})

    if not url or not segments:
        return jsonify({"error": "URL and segments are required"}), 400

    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "total": len(segments),
        "clips": [],
        "errors": [],
    }

    # Run in background
    executor.submit(
        _generate_clips_job,
        job_id, url, video_id, segments,
        aspect_ratio, crop_mode, sub_config,
    )

    return jsonify({"job_id": job_id, "status": "started"})


def _generate_clips_job(
    job_id, url, video_id, segments,
    aspect_ratio, crop_mode, sub_config,
):
    """Background job: download video + generate all clips."""
    try:
        # Step 1: Download video
        video_path = clipper.download_video(url, video_id)
        if not video_path:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["errors"].append("Failed to download video")
            return

        jobs[job_id]["status"] = "processing"

        # Get video dimensions for cropping
        in_w, in_h = clipper.get_video_dimensions(video_path)
        out_dims = clipper.ASPECT_RATIOS.get(aspect_ratio, (720, 1280))
        out_w, out_h = out_dims if out_dims else (in_w, in_h)

        # Prepare crop filter
        crop_filter = None
        if crop_mode == "ai_face":
            # Track faces for AI crop
            try:
                positions = cropper.track_speaker(video_path)
                if positions:
                    positions = cropper.smooth_crop_trajectory(positions)
                    crop_filter = cropper.generate_face_crop_filter(
                        positions, in_w, in_h, out_w, out_h
                    )
            except Exception as e:
                logger.warning("Face tracking failed, using center crop: %s", e)

        if not crop_filter and crop_mode != "center":
            crop_filter = cropper.get_crop_filter(
                crop_mode, in_w, in_h, out_w, out_h
            )
        elif not crop_filter:
            crop_filter = cropper.get_crop_filter(
                "center", in_w, in_h, out_w, out_h
            )

        # Generate clips
        for i, seg in enumerate(segments):
            try:
                clip_name = f"{video_id}_clip_{i+1}_{job_id}"
                output_path = str(CLIPS_DIR / f"{clip_name}.mp4")

                # Generate subtitles if enabled
                sub_path = None
                if sub_config.get("enabled", False):
                    try:
                        # Coerce empty string language to None for auto-detection
                        sub_lang = sub_config.get("language") or None
                        sub_result = subtitle.generate_subtitles_for_clip(
                            video_path,
                            seg["start"],
                            seg["end"],
                            str(CLIPS_DIR),
                            clip_name,
                            model_size=sub_config.get("model", "base"),
                            language=sub_lang,
                            style_config={
                                "font": sub_config.get("font", "Plus Jakarta Sans"),
                                "font_size": int(sub_config.get("font_size", 58)),
                                "position": sub_config.get("position", "bottom"),
                            },
                        )
                        if sub_result["success"]:
                            sub_path = sub_result["subtitle_path"]
                    except Exception as e:
                        logger.warning("Subtitle generation failed for clip %d: %s", i + 1, e)

                # Check if crop_filter is a complex filter (contains [])
                if crop_filter and "[" in crop_filter:
                    # Complex filter — use -filter_complex
                    result = _generate_clip_complex(
                        video_path, seg["start"], seg["end"],
                        output_path, crop_filter, sub_path,
                    )
                else:
                    result = clipper.generate_clip(
                        video_path, seg["start"], seg["end"],
                        output_path,
                        aspect_ratio=aspect_ratio,
                        crop_filter=crop_filter,
                        subtitle_path=sub_path,
                    )

                if result["success"]:
                    jobs[job_id]["clips"].append({
                        "filename": f"{clip_name}.mp4",
                        "start": seg["start"],
                        "end": seg["end"],
                        "url": f"/clips/{clip_name}.mp4",
                    })
                else:
                    jobs[job_id]["errors"].append(
                        f"Clip {i+1} failed: {result.get('error', 'Unknown')}"
                    )

            except Exception as e:
                jobs[job_id]["errors"].append(f"Clip {i+1} error: {str(e)}")

            jobs[job_id]["progress"] = i + 1

        jobs[job_id]["status"] = "completed"

    except Exception as e:
        logger.error("Job %s failed: %s", job_id, e)
        jobs[job_id]["status"] = "error"
        jobs[job_id]["errors"].append(str(e))


def _generate_clip_complex(
    input_path, start, end, output_path, complex_filter, subtitle_path=None
):
    """Generate a clip using FFmpeg -filter_complex for split layouts."""
    duration = end - start

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-filter_complex", complex_filter,
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
        return {"success": False, "output": output_path, "error": result.stderr[-500:]}
    except Exception as e:
        return {"success": False, "output": output_path, "error": str(e)}


@app.route("/api/status/<job_id>", methods=["GET"])
def api_job_status(job_id):
    """Poll job progress."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/manual-clip", methods=["POST"])
def api_manual_clip():
    """
    Generate a clip from manual time range.

    Body: {\"url\": str, \"start\": float, \"end\": float, ...settings}
    """
    data = request.get_json(force=True)
    url = data.get("url", "")
    start = float(data.get("start", 0))
    end = float(data.get("end", 0))

    if not url or end <= start:
        return jsonify({"error": "Valid URL and time range required"}), 400

    # Reuse /api/clips with a single segment
    data["segments"] = [{"start": start, "end": end}]
    data["video_id"] = clipper.extract_video_id(url) or "manual"

    # Forward to clips endpoint logic
    return api_create_clips()


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """
    Batch process a playlist or channel.

    Body: {\"url\": str}
    """
    data = request.get_json(force=True)
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400

    videos = clipper.list_playlist_videos(url)
    if not videos:
        return jsonify({"error": "No videos found in playlist/channel"}), 400

    return jsonify({
        "videos": videos,
        "count": len(videos),
    })


@app.route("/api/telegram/send", methods=["POST"])
def api_telegram_send():
    """
    Send a clip to Telegram.

    Body: {\"bot_token\": str, \"chat_id\": str, \"filename\": str, \"caption\": str}
    """
    data = request.get_json(force=True)
    bot_token = data.get("bot_token", "")
    chat_id = data.get("chat_id", "")
    filename = data.get("filename", "")
    caption = data.get("caption", "")

    file_path = CLIPS_DIR / filename
    if not file_path.exists():
        return jsonify({"error": "Clip not found"}), 404

    result = telegram_bot.send_clip(bot_token, chat_id, str(file_path), caption)
    status = 200 if result["success"] else 400
    return jsonify(result), status


@app.route("/clips/<path:filename>")
def serve_clip(filename):
    """Serve generated clips."""
    return send_from_directory(str(CLIPS_DIR), filename)


@app.route("/api/fonts", methods=["GET"])
def api_fonts():
    """List available fonts."""
    custom_fonts = []
    if FONTS_DIR.exists():
        for f in FONTS_DIR.iterdir():
            if f.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2"):
                custom_fonts.append(f.stem)

    return jsonify({
        "builtin": subtitle.AVAILABLE_FONTS,
        "custom": custom_fonts,
    })


@app.route("/api/models", methods=["GET"])
def api_models():
    """List available whisper models."""
    return jsonify({"models": subtitle.AVAILABLE_MODELS})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
def print_banner():
    """Print startup banner with system check results."""
    # Fix Windows console encoding for emoji/unicode
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print("\n" + "=" * 60)
    print("  🎬 AI Viral YouTube Heatmap Clipper")
    print("=" * 60)

    checks = check_system()
    all_ok = True
    for name, info in checks.items():
        status = "✅" if info["ok"] else "❌"
        print(f"  {status} {name}: {info['version']}")
        if not info["ok"]:
            all_ok = False

    if not all_ok:
        print("\n  ⚠️  Missing dependencies! Install instructions:")
        if not checks["ffmpeg"]["ok"]:
            print("     FFmpeg: https://ffmpeg.org/download.html")
            print("     Or: sudo apt install ffmpeg  (Linux)")
        if not checks["yt_dlp"]["ok"]:
            print("     yt-dlp: pip install yt-dlp")

    port = int(os.environ.get("PORT", 5000))
    print(f"\n  🌐 Web UI: http://0.0.0.0:{port}")
    print("=" * 60 + "\n")
    return port


if __name__ == "__main__":
    port = print_banner()
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "1") == "1")
