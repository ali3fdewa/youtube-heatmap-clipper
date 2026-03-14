"""
telegram_bot.py — Telegram Bot Integration

Sends generated clips to a Telegram chat via the Bot API.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendVideo"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB Telegram limit


def send_clip(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
) -> dict:
    """
    Send a video clip to a Telegram chat.

    Args:
        bot_token: Telegram Bot API token
        chat_id: Target chat ID
        file_path: Path to the video file
        caption: Optional message caption

    Returns:
        {\"success\": bool, \"message\": str}
    """
    if not bot_token or not chat_id:
        return {"success": False, "message": "Bot token and chat ID are required"}

    if not os.path.exists(file_path):
        return {"success": False, "message": f"File not found: {file_path}"}

    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        return {
            "success": False,
            "message": f"File too large ({file_size / 1024 / 1024:.1f} MB). "
                       f"Telegram limit is 50 MB.",
        }

    url = TELEGRAM_API_URL.format(token=bot_token)

    try:
        with open(file_path, "rb") as video_file:
            files = {"video": (os.path.basename(file_path), video_file, "video/mp4")}
            data = {
                "chat_id": chat_id,
                "caption": caption[:1024] if caption else "",
                "supports_streaming": True,
            }

            response = requests.post(url, data=data, files=files, timeout=120)
            result = response.json()

            if result.get("ok"):
                logger.info("Clip sent to Telegram chat %s", chat_id)
                return {"success": True, "message": "Clip sent successfully"}
            else:
                error = result.get("description", "Unknown error")
                logger.error("Telegram API error: %s", error)
                return {"success": False, "message": f"Telegram error: {error}"}

    except requests.exceptions.Timeout:
        return {"success": False, "message": "Upload timed out"}
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return {"success": False, "message": f"Send failed: {str(e)}"}


def validate_bot_token(bot_token: str) -> dict:
    """
    Validate a Telegram bot token by calling getMe.

    Returns {\"valid\": bool, \"bot_name\": str | None}
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        result = response.json()

        if result.get("ok"):
            bot_info = result.get("result", {})
            return {
                "valid": True,
                "bot_name": bot_info.get("first_name", "Unknown"),
            }
        return {"valid": False, "bot_name": None}
    except Exception:
        return {"valid": False, "bot_name": None}
