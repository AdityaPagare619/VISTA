"""
VISTA Telegram Alert Bot — Primary Alert Channel (v3.0)
========================================================
Sends crash, theft, and system alerts via the Telegram Bot API.

v3.0 design decision:
    - Telegram is PRIMARY (free, unlimited, developer-friendly)
    - Uses raw HTTP requests (no extra dependency beyond `requests`)
    - Every alert includes a safety disclaimer
    - Supports text + photo alerts
    - Exponential backoff on failure (3 retries max)
    - Chat ID from env var or file (auto-saved on first /start)

Usage::

    bot = TelegramAlertBot()
    bot.send_crash_alert(
        confidence=0.87,
        explanation="IMU: 8.2 g/s jerk, Audio: 'crash' at 91%",
        image_bytes=jpeg_data,  # optional
    )
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

# HTTP client (requests is almost always available; fallback to urllib)
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    import urllib.request
    import urllib.error
    import json as _json


class TelegramAlertBot:
    """Sends VISTA alerts through the Telegram Bot API.

    Thread-safe. All methods are non-blocking (timeout-guarded).
    """

    _API_BASE = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self) -> None:
        cfg = self._load_config()
        telegram_cfg = cfg.get("cloud", {}).get("alerts", {}).get("telegram", {})

        self._enabled: bool = telegram_cfg.get("enabled", True)

        # Bot token from environment
        token_env = telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
        self._token: str = os.environ.get(token_env, "")

        # Chat ID: try env first, then file
        chat_id_env = telegram_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID")
        self._chat_id: str = os.environ.get(chat_id_env, "")

        if not self._chat_id:
            chat_id_file = telegram_cfg.get("chat_id_file", "data/telegram_chat_id.txt")
            chat_id_path = Path(__file__).resolve().parent.parent / chat_id_file
            if chat_id_path.exists():
                self._chat_id = chat_id_path.read_text().strip()
                logger.debug(f"Telegram chat_id loaded from {chat_id_path}")

        # Safety disclaimer (v3.0 requirement)
        system_cfg = cfg.get("system", {})
        self._disclaimer: str = system_cfg.get(
            "safety_disclaimer",
            "⚠️ VISTA is a research prototype. Call emergency services if needed.",
        )

        # Retry config
        self._max_retries: int = 3
        self._timeout: float = 10.0

        if not self._token:
            logger.warning(
                "TelegramAlertBot: No bot token found — alerts will be logged only"
            )
        elif not self._chat_id:
            logger.warning(
                "TelegramAlertBot: No chat_id — send /start to your bot first"
            )
        else:
            logger.info(
                f"TelegramAlertBot initialized | chat_id={self._chat_id[:4]}*** | "
                f"disclaimer=enabled"
            )

    # ── Config loader ────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"config.yaml not found at {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ── Alert Methods ────────────────────────────────────────────

    def send_crash_alert(
        self,
        confidence: float,
        explanation: str,
        severity: str = "critical",
        location: Optional[Dict[str, float]] = None,
        image_bytes: Optional[bytes] = None,
    ) -> bool:
        """Send a crash detection alert.

        Args:
            confidence: Crash confidence [0, 1].
            explanation: Human-readable evidence breakdown.
            severity: "critical", "warning", or "info".
            location: Optional dict with "lat", "lon" keys.
            image_bytes: Optional JPEG image data from camera burst.

        Returns:
            True if sent successfully, False otherwise.
        """
        # Build message
        severity_emoji = {
            "critical": "🚨",
            "warning": "⚠️",
            "info": "ℹ️",
        }.get(severity, "🚨")

        lines = [
            f"{severity_emoji} *VISTA CRASH ALERT* {severity_emoji}",
            f"Severity: *{severity.upper()}*",
            f"Confidence: *{confidence:.0%}*",
            "",
            "📊 *Evidence:*",
            f"```\n{explanation}\n```",
        ]

        if location and "lat" in location and "lon" in location:
            lat, lon = location["lat"], location["lon"]
            lines.append(f"📍 Location: [{lat:.6f}, {lon:.6f}]"
                        f"(https://maps.google.com/?q={lat},{lon})")

        lines.extend([
            "",
            f"_{self._disclaimer}_",
            f"_Time: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        ])

        message = "\n".join(lines)

        if image_bytes:
            return self._send_photo(message, image_bytes)
        return self._send_message(message)

    def send_theft_alert(
        self,
        description: str,
        image_bytes: Optional[bytes] = None,
    ) -> bool:
        """Send a theft/intrusion detection alert."""
        lines = [
            "🔓 *VISTA THEFT ALERT* 🔓",
            "",
            description,
            "",
            f"_{self._disclaimer}_",
            f"_Time: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        ]

        message = "\n".join(lines)

        if image_bytes:
            return self._send_photo(message, image_bytes)
        return self._send_message(message)

    def send_system_alert(self, title: str, body: str) -> bool:
        """Send a system status alert (battery low, thermal, etc.)."""
        lines = [
            f"🔧 *VISTA: {title}*",
            "",
            body,
            "",
            f"_{self._disclaimer}_",
        ]
        return self._send_message("\n".join(lines))

    def send_test(self) -> bool:
        """Send a test message to verify bot configuration."""
        return self._send_message(
            "✅ *VISTA Telegram Bot Connected*\n\n"
            "Your VISTA system is linked to this chat.\n"
            "You will receive crash, theft, and system alerts here.\n\n"
            f"_{self._disclaimer}_"
        )

    # ── Internal: HTTP Communication ─────────────────────────────

    def _send_message(self, text: str) -> bool:
        """Send a text message via Telegram Bot API."""
        if not self._can_send():
            logger.info(f"[TELEGRAM-LOG] {text[:200]}...")
            return False

        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        return self._api_call("sendMessage", json_data=payload)

    def _send_photo(self, caption: str, image_bytes: bytes) -> bool:
        """Send a photo with caption via Telegram Bot API."""
        if not self._can_send():
            logger.info(f"[TELEGRAM-LOG] Photo + {caption[:100]}...")
            return False

        if not _HAS_REQUESTS:
            # Fallback: send text only
            logger.warning("requests not installed — sending text-only alert")
            return self._send_message(caption + "\n\n(Image could not be attached)")

        url = self._API_BASE.format(token=self._token, method="sendPhoto")

        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    url,
                    data={
                        "chat_id": self._chat_id,
                        "caption": caption,
                        "parse_mode": "Markdown",
                    },
                    files={"photo": ("crash.jpg", image_bytes, "image/jpeg")},
                    timeout=self._timeout,
                )
                if resp.status_code == 200:
                    logger.info("Telegram photo alert sent successfully")
                    return True
                logger.warning(
                    f"Telegram photo failed (attempt {attempt + 1}): "
                    f"{resp.status_code} {resp.text[:200]}"
                )
            except Exception as exc:
                logger.warning(
                    f"Telegram photo error (attempt {attempt + 1}): {exc}"
                )

            if attempt < self._max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff

        return False

    def _api_call(self, method: str, json_data: Dict[str, Any]) -> bool:
        """Make an API call with retry and exponential backoff."""
        url = self._API_BASE.format(token=self._token, method=method)

        for attempt in range(self._max_retries):
            try:
                if _HAS_REQUESTS:
                    resp = requests.post(
                        url, json=json_data, timeout=self._timeout
                    )
                    if resp.status_code == 200:
                        logger.info(f"Telegram {method} sent successfully")
                        return True
                    logger.warning(
                        f"Telegram {method} failed (attempt {attempt + 1}): "
                        f"{resp.status_code}"
                    )
                else:
                    # urllib fallback
                    data = _json.dumps(json_data).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={"Content-Type": "application/json"},
                    )
                    resp = urllib.request.urlopen(req, timeout=self._timeout)
                    if resp.status == 200:
                        logger.info(f"Telegram {method} sent successfully")
                        return True

            except Exception as exc:
                logger.warning(
                    f"Telegram {method} error (attempt {attempt + 1}): {exc}"
                )

            if attempt < self._max_retries - 1:
                time.sleep(2 ** attempt)

        logger.error(f"Telegram {method} failed after {self._max_retries} attempts")
        return False

    def _can_send(self) -> bool:
        """Check if we have both token and chat_id configured."""
        if not self._enabled:
            return False
        if not self._token:
            logger.debug("Telegram: no bot token configured")
            return False
        if not self._chat_id:
            logger.debug("Telegram: no chat_id configured")
            return False
        return True

    # ── Lifecycle ────────────────────────────────────────────────

    def stop(self) -> None:
        """Cleanup (no persistent resources to release)."""
        logger.info("TelegramAlertBot stopped")
