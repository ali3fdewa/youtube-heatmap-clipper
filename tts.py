"""
tts.py — AI Text-to-Speech Engine (Local AMD MI300X Optimized)

Provides asynchronous TTS generation for transcript segments.
Uses edge-tts as a lightweight fallback, but is designed to be easily 
extended to local models (like Coqui-TTS/XTTS) given the MI300X capabilities.
"""

import os
import asyncio
import logging
from pathlib import Path
import subprocess

logger = logging.getLogger(__name__)

# Try to import edge-tts for lightweight fast TTS
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge-tts not installed. Install with: pip install edge-tts")

# Define available local / lightweight voice models
AVAILABLE_VOICES = [
    # Edge-TTS voices (require internet, but very fast/high quality)
    {"id": "en-US-ChristopherNeural", "name": "Christopher (US Male - Deep)", "type": "edge"},
    {"id": "en-US-JennyNeural", "name": "Jenny (US Female - Cheerful)", "type": "edge"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (UK Female - Professional)", "type": "edge"},
    {"id": "en-US-GuyNeural", "name": "Guy (US Male - Enthusiastic)", "type": "edge"},
    {"id": "id-ID-ArdiNeural", "name": "Ardi (ID Male)", "type": "edge"},
    {"id": "id-ID-GadisNeural", "name": "Gadis (ID Female)", "type": "edge"},
]

DEFAULT_VOICE = "en-US-ChristopherNeural"

async def _generate_audio_edge(text: str, voice_id: str, output_path: str) -> bool:
    """Generate audio using Edge-TTS."""
    if not EDGE_TTS_AVAILABLE:
        logger.error("edge-tts is not installed.")
        return False
    try:
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(output_path)
        return True
    except Exception as e:
        logger.error("Edge-TTS generation failed: %s", e)
        return False

def generate_tts_for_segment(text: str, voice_id: str, output_path: str) -> bool:
    """
    Synchronous wrapper to generate TTS for a text segment.
    """
    if not text.strip():
        return False
        
    voice_type = "edge"
    for v in AVAILABLE_VOICES:
        if v["id"] == voice_id:
            voice_type = v["type"]
            break
            
    try:
        if voice_type == "edge":
            # Run the async edge-tts code
            asyncio.run(_generate_audio_edge(text, voice_id, output_path))
            return os.path.exists(output_path)
        else:
            logger.error("Unsupported voice type: %s", voice_type)
            return False
    except Exception as e:
        logger.error("TTS generation failed: %s", e)
        return False

def combine_tts_audio_with_video(video_path: str, tts_audio_path: str, output_path: str) -> bool:
    """
    Replace the video's original audio with the generated TTS audio.
    Assumes the TTS audio is already timed appropriately or we just want 
    it to play from the start of the video.
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", tts_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest", 
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True
        logger.error("FFmpeg TTS combine failed: %s", result.stderr)
        return False
    except Exception as e:
        logger.error("FFmpeg TTS combination error: %s", e)
        return False
