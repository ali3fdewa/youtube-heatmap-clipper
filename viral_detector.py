"""
viral_detector.py — Transcript-Based Viral Moment Detection

Analyzes transcripts from faster-whisper for viral triggers such as
surprise phrases, shouting, dramatic pauses, and question hooks.
Combines heatmap score with transcript score into a unified viral_score.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Viral trigger dictionaries
# ---------------------------------------------------------------------------
SURPRISE_PHRASES = [
    "you won't believe",
    "you would not believe",
    "this is crazy",
    "this is insane",
    "wait what",
    "what the",
    "oh my god",
    "oh my gosh",
    "no way",
    "are you serious",
    "are you kidding",
    "i can't believe",
    "holy",
    "unbelievable",
    "unreal",
    "that's insane",
    "mind blown",
    "mind blowing",
    "jaw dropping",
    "shocking",
    "plot twist",
    "tidak percaya",     # Indonesian
    "gila",              # Indonesian
    "astaga",            # Indonesian
]

HOOK_PHRASES = [
    "the secret is",
    "here's why",
    "here is why",
    "here's the thing",
    "let me tell you",
    "listen to this",
    "watch this",
    "check this out",
    "pay attention",
    "the truth is",
    "what if i told you",
    "the reason is",
    "number one",
    "first of all",
    "most people don't know",
    "the trick is",
    "pro tip",
    "life hack",
    "rahasia",           # Indonesian
    "caranya",           # Indonesian
]

LAUGHTER_INDICATORS = [
    "haha",
    "hehe",
    "lol",
    "lmao",
    "rofl",
    "😂",
    "🤣",
    "[laughter]",
    "[laughing]",
    "wkwk",              # Indonesian
]

QUESTION_HOOKS = [
    "how do you",
    "how does",
    "why do",
    "why does",
    "what happens if",
    "what happens when",
    "what would happen",
    "did you know",
    "have you ever",
    "can you believe",
    "is it possible",
    "would you rather",
    "kenapa",            # Indonesian
    "bagaimana",         # Indonesian
]

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------
HEATMAP_WEIGHT = 0.6
TRANSCRIPT_WEIGHT = 0.4

TRIGGER_WEIGHTS = {
    "surprise": 0.30,
    "hook": 0.20,
    "laughter": 0.15,
    "question": 0.15,
    "shouting": 0.10,
    "pause": 0.10,
}


# ---------------------------------------------------------------------------
# Transcript analysis functions
# ---------------------------------------------------------------------------
def _detect_surprise(text: str) -> float:
    """Score surprise phrases in text (0.0 – 1.0)."""
    text_lower = text.lower()
    hits = sum(1 for phrase in SURPRISE_PHRASES if phrase in text_lower)
    return min(hits / 3.0, 1.0)


def _detect_hooks(text: str) -> float:
    """Score hook phrases in text (0.0 – 1.0)."""
    text_lower = text.lower()
    hits = sum(1 for phrase in HOOK_PHRASES if phrase in text_lower)
    return min(hits / 2.0, 1.0)


def _detect_laughter(text: str) -> float:
    """Score laughter indicators (0.0 – 1.0)."""
    text_lower = text.lower()
    hits = sum(1 for indicator in LAUGHTER_INDICATORS if indicator in text_lower)
    return min(hits / 2.0, 1.0)


def _detect_questions(text: str) -> float:
    """Score question hooks (0.0 – 1.0)."""
    text_lower = text.lower()
    hits = sum(1 for q in QUESTION_HOOKS if q in text_lower)
    question_marks = text.count("?")
    return min((hits + question_marks * 0.3) / 2.0, 1.0)


def _detect_shouting(text: str) -> float:
    """Detect shouting via uppercase ratio and exclamation marks (0.0 – 1.0)."""
    if len(text) < 5:
        return 0.0

    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return 0.0

    upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
    excl_count = text.count("!")

    score = 0.0
    if upper_ratio > 0.6:
        score += 0.6
    if excl_count >= 2:
        score += 0.4

    return min(score, 1.0)


def _detect_dramatic_pause(segments: list[dict], index: int) -> float:
    """
    Detect dramatic pauses by looking at gaps between transcript segments.

    A gap > 1.5 seconds before a segment indicates a dramatic pause.
    """
    if index == 0 or len(segments) < 2:
        return 0.0

    current = segments[index]
    previous = segments[index - 1]

    gap = current.get("start", 0) - previous.get("end", 0)

    if gap > 3.0:
        return 1.0
    elif gap > 2.0:
        return 0.7
    elif gap > 1.5:
        return 0.4

    return 0.0


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_segment_transcript(
    text: str,
    all_segments: list[dict] | None = None,
    segment_index: int = 0,
) -> dict:
    """
    Analyze a transcript segment for viral potential.

    Returns:
        {
            \"transcript_score\": float,
            \"triggers\": {\"surprise\": float, \"hook\": float, ...},
        }
    """
    triggers = {
        "surprise": _detect_surprise(text),
        "hook": _detect_hooks(text),
        "laughter": _detect_laughter(text),
        "question": _detect_questions(text),
        "shouting": _detect_shouting(text),
        "pause": 0.0,
    }

    if all_segments:
        triggers["pause"] = _detect_dramatic_pause(all_segments, segment_index)

    # Weighted sum
    transcript_score = sum(
        triggers[key] * TRIGGER_WEIGHTS[key] for key in TRIGGER_WEIGHTS
    )

    return {
        "transcript_score": round(min(transcript_score, 1.0), 3),
        "triggers": {k: round(v, 3) for k, v in triggers.items()},
    }


def compute_viral_score(heatmap_score: float, transcript_score: float) -> float:
    """Combine heatmap and transcript scores into a unified viral score."""
    score = (HEATMAP_WEIGHT * heatmap_score) + (TRANSCRIPT_WEIGHT * transcript_score)
    return round(min(score, 1.0), 3)


def analyze_transcript_for_segments(
    transcript_segments: list[dict],
    heatmap_segments: list[dict],
) -> list[dict]:
    """
    Analyze full transcript against heatmap segments.

    For each heatmap segment, gather overlapping transcript text,
    compute transcript score, and produce viral_score.

    Args:
        transcript_segments: [{\"start\": float, \"end\": float, \"text\": str}, ...]
        heatmap_segments: [{\"start\": float, \"end\": float, \"score\": float}, ...]

    Returns:
        Updated heatmap_segments with added keys:
        - transcript_score
        - viral_score
        - triggers
    """
    results = []

    for seg in heatmap_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]

        # Gather transcript text overlapping this segment
        overlap_texts = []
        overlap_segs = []
        for i, ts in enumerate(transcript_segments):
            ts_start = ts.get("start", 0)
            ts_end = ts.get("end", 0)
            if ts_start < seg_end and ts_end > seg_start:
                overlap_texts.append(ts.get("text", ""))
                overlap_segs.append(ts)

        combined_text = " ".join(overlap_texts)

        analysis = analyze_segment_transcript(
            combined_text,
            all_segments=transcript_segments,
            segment_index=0,
        )

        viral_score = compute_viral_score(
            seg["score"], analysis["transcript_score"]
        )

        results.append({
            **seg,
            "transcript_score": analysis["transcript_score"],
            "viral_score": viral_score,
            "triggers": analysis["triggers"],
        })

    # Sort by viral_score descending
    results.sort(key=lambda x: x["viral_score"], reverse=True)
    return results
