"""
subtitle.py — AI Subtitle Engine (faster-whisper)

Transcribes audio using faster-whisper, generates viral-style ASS subtitles,
and supports font/position/style customization.
"""

import os
import re
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
FONTS_DIR = BASE_DIR / "fonts"

# ---------------------------------------------------------------------------
# Whisper model sizes
# ---------------------------------------------------------------------------
AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_MODEL = "base"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
AVAILABLE_FONTS = [
    "Plus Jakarta Sans",
    "Roboto",
    "Montserrat",
    "Arial",
]

DEFAULT_FONT = "Plus Jakarta Sans"

# ---------------------------------------------------------------------------
# Viral subtitle style defaults
# ---------------------------------------------------------------------------
DEFAULT_STYLE = {
    "font": DEFAULT_FONT,
    "font_size": 58,
    "primary_color": "&H00FFFFFF",     # white
    "highlight_color": "&H0000FFFF",   # yellow (BGR)
    "outline_color": "&H00000000",     # black
    "shadow_color": "&H80000000",      # semi-transparent black
    "outline_width": 5,
    "shadow_depth": 3,
    "bold": True,
    "position": "bottom",             # "bottom" or "center"
    "margin_v": 180,
}

# Important words to highlight in yellow
HIGHLIGHT_WORDS = {
    "important", "secret", "amazing", "incredible", "unbelievable",
    "crazy", "insane", "shocking", "never", "always", "best", "worst",
    "first", "last", "only", "free", "new", "now", "today",
    "money", "million", "billion", "stop", "wait", "listen",
    "watch", "look", "warning", "danger", "truth", "lie",
    "penting", "rahasia", "gratis", "baru",  # Indonesian
}


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
def transcribe(
    audio_path: str,
    model_size: str = DEFAULT_MODEL,
    language: str | None = None,
) -> list[dict]:
    """
    Transcribe audio using faster-whisper.

    Returns list of segments: [{\"start\": float, \"end\": float, \"text\": str, \"words\": [...]}]
    """
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        # Coerce empty string to None for auto-detection
        if not language:
            language = None

        segments, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
        )

        logger.info("Detected language: %s (prob: %.2f)", info.language, info.language_probability)

        result = []
        for segment in segments:
            words = []
            if segment.words:
                for w in segment.words:
                    words.append({
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "word": w.word.strip(),
                    })

            result.append({
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text.strip(),
                "words": words,
            })

        return result
    except ImportError:
        logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
        return []
    except Exception as e:
        logger.error("Transcription failed: %s", e)
        return []


def extract_audio(video_path: str, output_path: str | None = None) -> str | None:
    """Extract audio from video using FFmpeg."""
    if not output_path:
        output_path = video_path.rsplit(".", 1)[0] + ".wav"

    if os.path.exists(output_path):
        return output_path

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return output_path
        logger.error("Audio extraction failed: %s", result.stderr[-300:])
        return None
    except Exception as e:
        logger.error("Audio extraction error: %s", e)
        return None


# ---------------------------------------------------------------------------
# ASS subtitle generation
# ---------------------------------------------------------------------------
def _ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _colorize_text(text: str, highlight_color: str, primary_color: str) -> str:
    """
    Apply viral-style coloring: highlight important words in yellow,
    rest in white. All text is uppercased for viral impact.
    Uses ASS override tags.
    """
    words = text.upper().split()
    result = []
    for word in words:
        clean = re.sub(r"[^\w]", "", word).lower()
        if clean in HIGHLIGHT_WORDS:
            result.append(f"{{\\c{highlight_color}\\b1}}{word}{{\\c{primary_color}\\b1}}")
        else:
            result.append(word)
    return " ".join(result)


def generate_ass_subtitle(
    segments: list[dict],
    style_config: dict | None = None,
    offset: float = 0.0,
) -> str:
    """
    Generate an ASS (Advanced SubStation Alpha) subtitle string.

    Supports viral styling with highlighted important words.
    """
    cfg = {**DEFAULT_STYLE, **(style_config or {})}

    alignment = "2" if cfg["position"] == "bottom" else "5"
    bold_flag = "-1" if cfg["bold"] else "0"

    ass_content = f"""[Script Info]
Title: AI Viral Subtitles
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg['font']},{cfg['font_size']},{cfg['primary_color']},&H000000FF,{cfg['outline_color']},{cfg['shadow_color']},{bold_flag},0,0,0,100,100,0,0,1,{cfg['outline_width']},{cfg['shadow_depth']},{alignment},20,20,{cfg['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for seg in segments:
        start = seg["start"] - offset
        end = seg["end"] - offset
        if start < 0:
            start = 0

        text = seg.get("text", "")
        # Apply viral coloring
        styled_text = _colorize_text(
            text, cfg["highlight_color"], cfg["primary_color"]
        )

        # Add pop-in animation effect
        fade = "{\\fad(150,100)}"
        line = f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,{fade}{styled_text}"
        ass_content += line + "\n"

    return ass_content


def save_subtitle_file(
    segments: list[dict],
    output_path: str,
    style_config: dict | None = None,
    offset: float = 0.0,
) -> str:
    """Generate and save ASS subtitle file. Returns the file path."""
    ass_content = generate_ass_subtitle(segments, style_config, offset)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    logger.info("Subtitle saved: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Full pipeline: transcribe + generate subtitle file
# ---------------------------------------------------------------------------
def generate_subtitles_for_clip(
    video_path: str,
    clip_start: float,
    clip_end: float,
    output_dir: str,
    clip_name: str,
    model_size: str = DEFAULT_MODEL,
    language: str | None = None,
    style_config: dict | None = None,
) -> dict:
    """
    Full subtitle pipeline for a single clip.

    1. Extract audio from the segment
    2. Transcribe with faster-whisper
    3. Generate ASS subtitle file

    Returns {\"subtitle_path\": str, \"transcript\": list, \"success\": bool}
    """
    # Extract audio for the clip segment
    audio_path = os.path.join(output_dir, f"{clip_name}_audio.wav")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(clip_start),
            "-i", video_path,
            "-t", str(clip_end - clip_start),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            audio_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        logger.error("Audio extraction failed: %s", e)
        return {"subtitle_path": None, "transcript": [], "success": False}

    if not os.path.exists(audio_path):
        return {"subtitle_path": None, "transcript": [], "success": False}

    # Transcribe
    transcript = transcribe(audio_path, model_size=model_size, language=language)

    if not transcript:
        return {"subtitle_path": None, "transcript": [], "success": False}

    # Generate ASS file
    sub_path = os.path.join(output_dir, f"{clip_name}.ass")
    save_subtitle_file(transcript, sub_path, style_config=style_config, offset=0)

    # Cleanup audio
    try:
        os.remove(audio_path)
    except OSError:
        pass

    return {"subtitle_path": sub_path, "transcript": transcript, "success": True}
