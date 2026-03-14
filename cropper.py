"""
cropper.py — Video Crop Modes & OpenCV Face Detection/Tracking

Implements 6 crop modes including AI face tracking using OpenCV.
Generates FFmpeg filter strings for each mode.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Crop mode constants
# ---------------------------------------------------------------------------
CROP_MODES = [
    "center",
    "split_left",
    "split_right",
    "split_up_down",
    "split_left_right",
    "ai_face",
]

# OpenCV Haar cascade path
CASCADE_PATH = None  # Will be set on first use


def _get_cascade_path() -> str:
    """Get the path to OpenCV's Haar cascade for face detection."""
    global CASCADE_PATH
    if CASCADE_PATH is None:
        try:
            import cv2
            CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        except ImportError:
            CASCADE_PATH = ""
    return CASCADE_PATH


# ---------------------------------------------------------------------------
# Crop filter generators
# ---------------------------------------------------------------------------
def get_crop_filter(
    mode: str,
    input_w: int,
    input_h: int,
    output_w: int,
    output_h: int,
) -> str | None:
    """
    Generate an FFmpeg crop/scale filter string for the given mode.

    Args:
        mode: one of CROP_MODES
        input_w, input_h: source video dimensions
        output_w, output_h: target output dimensions

    Returns:
        FFmpeg filter string, or None for 'original' / 'ai_face' (handled separately)
    """
    if mode == "center":
        return _center_crop(input_w, input_h, output_w, output_h)
    elif mode == "split_left":
        return _split_left(input_w, input_h, output_w, output_h)
    elif mode == "split_right":
        return _split_right(input_w, input_h, output_w, output_h)
    elif mode == "split_up_down":
        return _split_up_down(input_w, input_h, output_w, output_h)
    elif mode == "split_left_right":
        return _split_left_right(input_w, input_h, output_w, output_h)
    elif mode == "ai_face":
        return None  # AI face tracking is handled via the face tracking pipeline
    else:
        return _center_crop(input_w, input_h, output_w, output_h)


def _center_crop(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """Center crop to match output aspect ratio."""
    target_ratio = out_w / out_h
    source_ratio = in_w / in_h

    if source_ratio > target_ratio:
        # Source is wider — crop width
        crop_w = int(in_h * target_ratio)
        crop_h = in_h
        x = (in_w - crop_w) // 2
        y = 0
    else:
        # Source is taller — crop height
        crop_w = in_w
        crop_h = int(in_w / target_ratio)
        x = 0
        y = (in_h - crop_h) // 2

    return f"crop={crop_w}:{crop_h}:{x}:{y}"


def _split_left(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """
    Split layout: top half = main content (center cropped),
    bottom half = bottom-left corner of source (facecam).
    """
    half_h = out_h // 2

    # Top: center crop of full source
    top_crop_w = int(in_h * (out_w / half_h))
    if top_crop_w > in_w:
        top_crop_w = in_w
    top_x = (in_w - top_crop_w) // 2

    # Bottom: bottom-left quadrant
    cam_w = in_w // 3
    cam_h = in_h // 3
    cam_x = 0
    cam_y = in_h - cam_h

    return (
        f"[0:v]crop={top_crop_w}:{in_h}:{top_x}:0,scale={out_w}:{half_h}[top];"
        f"[0:v]crop={cam_w}:{cam_h}:{cam_x}:{cam_y},scale={out_w}:{half_h}[bottom];"
        f"[top][bottom]vstack"
    )


def _split_right(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """
    Split layout: top half = main content,
    bottom half = bottom-right corner (facecam).
    """
    half_h = out_h // 2

    top_crop_w = int(in_h * (out_w / half_h))
    if top_crop_w > in_w:
        top_crop_w = in_w
    top_x = (in_w - top_crop_w) // 2

    cam_w = in_w // 3
    cam_h = in_h // 3
    cam_x = in_w - cam_w
    cam_y = in_h - cam_h

    return (
        f"[0:v]crop={top_crop_w}:{in_h}:{top_x}:0,scale={out_w}:{half_h}[top];"
        f"[0:v]crop={cam_w}:{cam_h}:{cam_x}:{cam_y},scale={out_w}:{half_h}[bottom];"
        f"[top][bottom]vstack"
    )


def _split_up_down(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """
    Split layout: top half = top of source (speaker),
    bottom half = bottom of source (gameplay).
    """
    half_h = out_h // 2
    src_half = in_h // 2

    return (
        f"[0:v]crop={in_w}:{src_half}:0:0,scale={out_w}:{half_h}[top];"
        f"[0:v]crop={in_w}:{src_half}:0:{src_half},scale={out_w}:{half_h}[bottom];"
        f"[top][bottom]vstack"
    )


def _split_left_right(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """
    Split layout: top half = left of source (gameplay),
    bottom half = right of source (speaker).
    Stacked vertically for 9:16 output.
    """
    half_h = out_h // 2
    src_half_w = in_w // 2

    return (
        f"[0:v]crop={src_half_w}:{in_h}:0:0,scale={out_w}:{half_h}[left];"
        f"[0:v]crop={src_half_w}:{in_h}:{src_half_w}:0,scale={out_w}:{half_h}[right];"
        f"[left][right]vstack"
    )


# ---------------------------------------------------------------------------
# OpenCV face detection
# ---------------------------------------------------------------------------
def detect_faces(frame) -> list[dict]:
    """
    Detect faces in a single frame using OpenCV Haar cascade.

    Args:
        frame: numpy array (BGR image)

    Returns:
        List of {\"x\": int, \"y\": int, \"w\": int, \"h\": int, \"area\": int}
    """
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed")
        return []

    cascade_path = _get_cascade_path()
    if not cascade_path:
        return []

    cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )

    results = []
    for (x, y, w, h) in faces:
        results.append({
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "area": int(w * h),
        })

    # Sort by area descending (largest face = main speaker)
    results.sort(key=lambda f: f["area"], reverse=True)
    return results


def track_speaker(
    video_path: str,
    start_time: float = 0,
    end_time: float | None = None,
    sample_interval: float = 0.5,
) -> list[dict]:
    """
    Track the main speaker's face across a video segment.

    Samples frames at the given interval, detects faces, and returns
    a list of face positions over time.

    Returns:
        [{\"time\": float, \"x\": int, \"y\": int, \"w\": int, \"h\": int}, ...]
    """
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not installed")
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Cannot open video: %s", video_path)
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    if end_time is None:
        end_time = duration

    positions = []
    current_time = start_time

    while current_time <= end_time:
        frame_num = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            break

        faces = detect_faces(frame)
        if faces:
            main_face = faces[0]  # Largest face
            positions.append({
                "time": round(current_time, 3),
                "x": main_face["x"],
                "y": main_face["y"],
                "w": main_face["w"],
                "h": main_face["h"],
            })
        elif positions:
            # No face detected — use last known position
            positions.append({
                "time": round(current_time, 3),
                **{k: positions[-1][k] for k in ("x", "y", "w", "h")},
            })

        current_time += sample_interval

    cap.release()
    return positions


def smooth_crop_trajectory(
    positions: list[dict],
    window: int = 5,
) -> list[dict]:
    """
    Smooth face tracking positions using a moving average.

    Produces a smoother camera movement for the crop.
    """
    if len(positions) < window:
        return positions

    smoothed = []
    for i in range(len(positions)):
        start = max(0, i - window // 2)
        end = min(len(positions), i + window // 2 + 1)
        window_slice = positions[start:end]

        avg_x = int(np.mean([p["x"] for p in window_slice]))
        avg_y = int(np.mean([p["y"] for p in window_slice]))
        avg_w = int(np.mean([p["w"] for p in window_slice]))
        avg_h = int(np.mean([p["h"] for p in window_slice]))

        smoothed.append({
            "time": positions[i]["time"],
            "x": avg_x,
            "y": avg_y,
            "w": avg_w,
            "h": avg_h,
        })

    return smoothed


def generate_face_crop_filter(
    positions: list[dict],
    input_w: int,
    input_h: int,
    output_w: int,
    output_h: int,
) -> str:
    """
    Generate an FFmpeg crop filter that dynamically follows the tracked face.

    For simplicity, uses the average face position to create a static crop
    centered on the speaker. For full dynamic tracking, a more complex
    filter with sendcmd or a Python-based frame processor would be needed.
    """
    if not positions:
        return _center_crop(input_w, input_h, output_w, output_h)

    # Smooth positions
    smoothed = smooth_crop_trajectory(positions)

    # Use average position for a stable crop
    avg_x = int(np.mean([p["x"] for p in smoothed]))
    avg_y = int(np.mean([p["y"] for p in smoothed]))
    avg_w = int(np.mean([p["w"] for p in smoothed]))
    avg_h = int(np.mean([p["h"] for p in smoothed]))

    # Face center
    face_cx = avg_x + avg_w // 2
    face_cy = avg_y + avg_h // 2

    # Target crop dimensions to match output aspect ratio
    target_ratio = output_w / output_h
    crop_h = input_h
    crop_w = int(crop_h * target_ratio)

    if crop_w > input_w:
        crop_w = input_w
        crop_h = int(crop_w / target_ratio)

    # Center crop on face
    crop_x = max(0, min(face_cx - crop_w // 2, input_w - crop_w))
    crop_y = max(0, min(face_cy - crop_h // 2, input_h - crop_h))

    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
