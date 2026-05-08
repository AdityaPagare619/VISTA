"""
VISTA Alert Manager
===================
Routes decision engine alerts through all configured channels based on
severity. The primary focus is Telegram (rich photo + caption), but the
system also routes through MQTT, BLE, and a physical buzzer.

Routing Rules
─────────────
  critical  → telegram + ble + mqtt + buzzer
  warning   → mqtt + ble
  info      → mqtt

Telegram Integration
────────────────────
- Uses raw ``requests`` to the Telegram Bot API (no library needed).
- Bot token from ``TELEGRAM_BOT_TOKEN`` environment variable.
- Chat ID is auto-captured when a user sends /start to the bot.
  Stored in ``data/telegram_chat_id.txt``.
- If no chat_id exists yet → log warning "No Telegram chat_id registered.
  Send /start to bot."

Every message includes:
  - Emoji based on event type
  - Event type + severity
  - Confidence percentage
  - Evidence breakdown (sensor → contribution)
  - GPS location (if available)
  - Timestamp
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from loguru import logger

from . import Decision, _is_demo_mode, _load_config

# ── Emoji Map ─────────────────────────────────────────────────────

_EVENT_EMOJI: Dict[str, str] = {
    "crash": "\U0001f4a5",           # 💥 collision
    "theft": "\U0001f6a8",           # 🚨 police light
    "harsh_braking": "\U0001f6d1",   # 🛑 stop sign
    "rapid_accel": "\U0001f680",     # 🚀 rocket
    "sharp_turn": "\U0001f500",      # 🔀 shuffle
    "overspeed": "\u26a1",           # ⚡ high voltage
    "intrusion": "\U0001f6aa",       # 🚪 door
    "fire": "\U0001f525",            # 🔥 fire
    "battery_low": "\U0001f50b",     # 🔋 battery
    "sos": "\U0001f198",             # 🆘 SOS
}

_SEVERITY_EMOJI: Dict[str, str] = {
    "critical": "\U0001f534",  # 🔴
    "warning": "\U0001f7e1",   # 🟡
    "info": "\U0001f7e2",      # 🟢
}


class AlertManager:
    """Multi-channel alert router for the VISTA decision engine.

    Decides where to send alerts based on severity and delivers them
    through Telegram, MQTT, BLE, and optionally a physical buzzer.

    Usage::

        mgr = AlertManager()
        mgr.set_mqtt_manager(mqtt)
        mgr.set_ble_manager(ble)
        mgr.send_alert(decision, image_bytes=b"...")
    """

    def __init__(self) -> None:
        cfg = _load_config()
        alert_cfg = cfg.get("cloud", {}).get("alerts", {})
        telegram_cfg = alert_cfg.get("telegram", {})

        self._demo_mode = _is_demo_mode()
        self._telegram_enabled: bool = telegram_cfg.get("enabled", True)

        # Telegram config
        self._bot_token: str = ""
        self._chat_id_file: Path = Path(
            telegram_cfg.get("chat_id_file", "data/telegram_chat_id.txt")
        )
        if not self._chat_id_file.is_absolute():
            package_root = Path(__file__).resolve().parent.parent
            self._chat_id_file = package_root / self._chat_id_file

        # Load bot token from env
        token_env_name = telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
        self._bot_token = os.environ.get(token_env_name, "").strip()

        # External manager references (set via setters)
        self._mqtt_manager: Any = None
        self._ble_manager: Any = None
        self._buzzer_callback: Optional[callable] = None  # callable(active: bool)

        # Optional: GPIOManager for buzzer control
        self._gpio_manager: Any = None
        try:
            from hal.gpio_manager import GPIOManager  # type: ignore
            self._gpio_manager = GPIOManager()
        except Exception:
            pass  # GPIO not available on all platforms

        # Cache chat ID so we don't re-read the file every alert
        self._cached_chat_id: Optional[str] = None
        self._chat_id_lock = __import__("threading").Lock()

        # Session for efficient requests
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

        logger.info(
            f"AlertManager initialized | telegram={'enabled' if self._telegram_enabled and self._bot_token else 'disabled'} | "
            f"demo={self._demo_mode}"
        )

        if not self._bot_token and self._telegram_enabled and not self._demo_mode:
            logger.warning(
                f"Telegram bot token not set. Set {token_env_name} in .env "
                f"or environment."
            )

    # ── Dependency Injection ───────────────────────────────────────

    def set_mqtt_manager(self, mqtt_manager: Any) -> None:
        """Inject the MQTT manager for alert routing."""
        self._mqtt_manager = mqtt_manager
        logger.debug("AlertManager: MQTT manager injected")

    def set_ble_manager(self, ble_manager: Any) -> None:
        """Inject the BLE manager for alert routing."""
        self._ble_manager = ble_manager
        logger.debug("AlertManager: BLE manager injected")

    def set_buzzer_callback(self, callback: callable) -> None:
        """Set a callback function for buzzer control.

        Callback signature: callback(active: bool) where True = on, False = off.
        """
        self._buzzer_callback = callback
        logger.debug("AlertManager: buzzer callback set")

    # ── Chat ID Management ─────────────────────────────────────────

    def _get_chat_id(self) -> Optional[str]:
        """Read the stored Telegram chat ID from disk (with caching).

        Returns the chat ID string or None if not registered.
        """
        # Return cached value if available
        if self._cached_chat_id is not None:
            return self._cached_chat_id

        with self._chat_id_lock:
            # Double-check under lock
            if self._cached_chat_id is not None:
                return self._cached_chat_id

            try:
                if self._chat_id_file.exists():
                    content = self._chat_id_file.read_text(encoding="utf-8").strip()
                    if content:
                        self._cached_chat_id = content
                        logger.debug(f"Loaded Telegram chat_id: {content}")
                        return content
            except Exception as exc:
                logger.error(f"Failed to read chat_id file: {exc}")

            return None

    def store_chat_id(self, chat_id: str) -> bool:
        """Store a Telegram chat ID to disk.

        Called when a user sends /start to the bot.
        Returns True on success.
        """
        if not chat_id or not chat_id.strip():
            logger.error("store_chat_id: empty chat_id")
            return False

        chat_id = chat_id.strip()
        with self._chat_id_lock:
            try:
                self._chat_id_file.parent.mkdir(parents=True, exist_ok=True)
                self._chat_id_file.write_text(chat_id, encoding="utf-8")
                self._cached_chat_id = chat_id
                logger.success(f"Telegram chat_id stored: {chat_id}")
                return True
            except Exception as exc:
                logger.error(f"Failed to store chat_id: {exc}")
                return False

    # ── Main Alert Routing ─────────────────────────────────────────

    def send_alert(
        self,
        decision: Decision,
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, bool]:
        """Route a decision alert through all appropriate channels.

        Args:
            decision: The Decision object from the intelligence engine.
            image_bytes: Optional JPEG image bytes for the alert photo.

        Returns:
            Dict mapping channel name → success status.
        """
        severity = decision.severity.lower()
        results: Dict[str, bool] = {}

        logger.info(
            f"Alert routing | type={decision.event_type} | "
            f"severity={severity} | confidence={decision.confidence:.1%}"
        )

        if severity == "critical":
            results["telegram"] = self.send_telegram_alert(decision, image_bytes)
            results["ble"] = self._send_ble_alert(decision)
            results["mqtt"] = self._send_mqtt_alert(decision)
            results["buzzer"] = self._activate_buzzer(decision)

        elif severity == "warning":
            results["mqtt"] = self._send_mqtt_alert(decision)
            results["ble"] = self._send_ble_alert(decision)

        elif severity == "info":
            results["mqtt"] = self._send_mqtt_alert(decision)

        else:
            logger.warning(f"Unknown severity '{severity}' — routing as info")
            results["mqtt"] = self._send_mqtt_alert(decision)

        # Log routing summary
        success_count = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(
            f"Alert routing complete | {success_count}/{total} channels succeeded | "
            f"results={results}"
        )

        return results

    # ── Telegram Alert ────────────────────────────────────────────

    def send_telegram_alert(
        self,
        decision: Decision,
        image_bytes: Optional[bytes] = None,
    ) -> bool:
        """Send a rich alert to Telegram with photo + caption.

        Uses the sendPhoto API endpoint with multipart form-data.
        Falls back to sendMessage if no image is available.

        Returns True if the message was sent successfully.
        """
        if self._demo_mode:
            logger.info(
                f"[DEMO] Telegram alert | {decision.event_type} | "
                f"confidence={decision.confidence:.1%} | "
                f"evidence={decision.evidence_summary}"
            )
            return True

        if not self._telegram_enabled:
            logger.debug("Telegram alerts disabled in config")
            return False

        if not self._bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        chat_id = self._get_chat_id()
        if not chat_id:
            logger.warning(
                "No Telegram chat_id registered. "
                "Send /start to the bot to register this device."
            )
            return False

        caption = self._build_telegram_caption(decision)

        try:
            if image_bytes:
                # Send photo with caption (multipart/form-data)
                return self._send_photo(chat_id, image_bytes, caption)
            else:
                # Send text-only message
                return self._send_message(chat_id, caption)

        except requests.exceptions.Timeout:
            logger.error("Telegram API timeout — network issue?")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("Telegram API connection error — offline?")
            return False
        except Exception as exc:
            logger.error(f"Telegram send_alert failed: {exc}")
            return False

    def _send_photo(self, chat_id: str, image_bytes: bytes, caption: str) -> bool:
        """Send a photo via the Telegram Bot API using multipart/form-data."""
        url = f"https://api.telegram.org/bot{self._bot_token}/sendPhoto"

        files = {
            "photo": ("alert.jpg", image_bytes, "image/jpeg"),
        }
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        }

        resp = self._session.post(
            url,
            data=data,
            files=files,
            timeout=15,
        )

        if resp.status_code == 200:
            result = resp.json()
            if result.get("ok"):
                logger.success(
                    f"Telegram photo sent | chat_id={chat_id} | "
                    f"size={len(image_bytes)} bytes"
                )
                return True
            else:
                logger.error(
                    f"Telegram API error: {result.get('description', 'unknown')}"
                )
                return False
        else:
            logger.error(
                f"Telegram HTTP {resp.status_code}: {resp.text[:300]}"
            )
            return False

    def _send_message(self, chat_id: str, text: str) -> bool:
        """Send a text-only message via Telegram."""
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        resp = self._session.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            result = resp.json()
            if result.get("ok"):
                logger.success(f"Telegram message sent | chat_id={chat_id}")
                return True
            else:
                logger.error(
                    f"Telegram API error: {result.get('description', 'unknown')}"
                )
                return False
        else:
            logger.error(f"Telegram HTTP {resp.status_code}: {resp.text[:300]}")
            return False

    # ── Caption Builder ────────────────────────────────────────────

    def _build_telegram_caption(self, decision: Decision) -> str:
        """Build a rich HTML-formatted caption for Telegram alerts."""
        emoji = _EVENT_EMOJI.get(decision.event_type, "\u2139\ufe0f")  # ℹ️ default
        sev_emoji = _SEVERITY_EMOJI.get(decision.severity, "\u26aa")  # ⚪ default

        lines = [
            f"{emoji} <b>VISTA Alert</b> {emoji}",
            "",
            f"{sev_emoji} <b>Event:</b> {decision.event_type.replace('_', ' ').title()}",
            f"{sev_emoji} <b>Severity:</b> {decision.severity.upper()}",
            f"\U0001f4ca <b>Confidence:</b> {decision.confidence:.1%}",
            "",
            "<b>Evidence:</b>",
        ]

        if decision.evidence:
            for sensor, contrib in sorted(
                decision.evidence.items(), key=lambda x: x[1], reverse=True
            ):
                bar = "\u2588" * int(contrib * 10) + "\u2591" * (10 - int(contrib * 10))
                lines.append(f"  {sensor}: {bar} {contrib:.1%}")
        else:
            lines.append("  No evidence breakdown available")

        lines.append("")

        if decision.location:
            lines.append(
                f"\U0001f4cd <b>Location:</b> {decision.location_str}"
            )
        else:
            lines.append("\U0001f4cd <b>Location:</b> Unknown")

        # Timestamp
        from datetime import datetime
        ts = datetime.fromtimestamp(decision.timestamp)
        lines.append(
            f"\U0001f552 <b>Time:</b> {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        # Device info
        cfg = _load_config()
        device_name = cfg.get("device", {}).get("name", "Unknown")
        device_id = cfg.get("device", {}).get("id", "Unknown")
        lines.append(f"\U0001f4f1 <b>Device:</b> {device_name} ({device_id})")

        # Footer
        lines.append("")
        lines.append("<i>— VISTA Intelligence System</i>")

        return "\n".join(lines)

    # ── Channel Handlers ───────────────────────────────────────────

    def _send_mqtt_alert(self, decision: Decision) -> bool:
        """Publish the alert via MQTT. Returns True if successful."""
        if self._mqtt_manager is None:
            logger.debug("MQTT manager not set — skipping MQTT alert")
            return False

        try:
            decision_dict = {
                "event_type": decision.event_type,
                "confidence": decision.confidence,
                "severity": decision.severity,
                "evidence": decision.evidence,
                "timestamp": decision.timestamp,
                "location": decision.location,
                "image_path": decision.image_path,
            }
            return self._mqtt_manager.publish_alert(decision_dict)
        except Exception as exc:
            logger.error(f"MQTT alert publish failed: {exc}")
            return False

    def _send_ble_alert(self, decision: Decision) -> bool:
        """Send alert notification via BLE. Returns True if successful."""
        if self._ble_manager is None:
            logger.debug("BLE manager not set — skipping BLE alert")
            return False

        try:
            message = (
                f"{decision.event_type.upper()} | "
                f"confidence={decision.confidence:.1%} | "
                f"severity={decision.severity}"
            )
            return self._ble_manager.send_alert(message)
        except Exception as exc:
            logger.error(f"BLE alert send failed: {exc}")
            return False

    def _activate_buzzer(self, decision: Decision) -> bool:
        """Activate the physical buzzer for critical alerts.

        Uses GPIOManager if available, or the buzzer callback.
        Returns True on success.
        """
        # Try GPIO manager first
        if self._gpio_manager is not None:
            try:
                # Pulse buzzer: 3 short beeps for alert
                import time
                for _ in range(3):
                    self._gpio_manager.buzzer_on()
                    time.sleep(0.2)
                    self._gpio_manager.buzzer_off()
                    time.sleep(0.1)
                logger.info("Buzzer activated (3 pulses)")
                return True
            except Exception as exc:
                logger.warning(f"GPIO buzzer failed: {exc}")

        # Try callback fallback
        if self._buzzer_callback is not None:
            try:
                self._buzzer_callback(True)
                logger.info("Buzzer activated via callback")
                return True
            except Exception as exc:
                logger.warning(f"Buzzer callback failed: {exc}")

        # In demo mode, it's OK
        if self._demo_mode:
            logger.info("[DEMO] Buzzer activated (simulated)")
            return True

        logger.warning("Buzzer not available — no GPIO manager or callback set")
        return False

    # ── Telegram Polling (for /start registration) ──────────────────

    def start_telegram_polling(self) -> None:
        """Start a background thread that polls for Telegram /start commands.

        When a user sends /start, their chat_id is captured and stored.
        This runs as a daemon thread with long polling.
        """
        import threading

        if self._demo_mode:
            logger.info("[DEMO] Telegram polling started (no-op)")
            return

        if not self._bot_token:
            logger.warning("Cannot start Telegram polling: no bot token")
            return

        thread = threading.Thread(
            target=self._telegram_poll_loop,
            name="telegram-poll",
            daemon=True,
        )
        thread.start()
        logger.info("Telegram polling started (waiting for /start)")

    def _telegram_poll_loop(self) -> None:
        """Long-polling loop for Telegram updates (handles /start)."""
        offset = 0

        while True:
            try:
                url = (
                    f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
                )
                resp = self._session.get(
                    url,
                    params={
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                    timeout=35,
                )

                if resp.status_code != 200:
                    logger.warning(
                        f"Telegram getUpdates HTTP {resp.status_code}"
                    )
                    time.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    logger.warning(
                        f"Telegram getUpdates error: "
                        f"{data.get('description', 'unknown')}"
                    )
                    time.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    text = message.get("text", "").strip().lower()
                    chat = message.get("chat", {})
                    chat_id = str(chat.get("id", ""))

                    if text == "/start" and chat_id:
                        self.store_chat_id(chat_id)
                        # Send confirmation
                        self._session.post(
                            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": (
                                    "\u2705 <b>VISTA Alert Bot Registered!</b>\n\n"
                                    "You will now receive vehicle alerts on this chat.\n\n"
                                    "Commands:\n"
                                    "/status - Check device status\n"
                                    "/arm - Arm the security system\n"
                                    "/disarm - Disarm the security system\n"
                                    "/snapshot - Request a camera snapshot\n"
                                    "/help - Show this help"
                                ),
                                "parse_mode": "HTML",
                            },
                            timeout=10,
                        )
                        logger.success(
                            f"Telegram /start received | chat_id={chat_id}"
                        )

            except requests.exceptions.Timeout:
                continue  # Long polling timeout is normal
            except requests.exceptions.ConnectionError:
                logger.warning("Telegram polling: connection error — retrying in 10s")
                time.sleep(10)
            except Exception as exc:
                logger.error(f"Telegram polling error: {exc}")
                time.sleep(5)

    # ── Status ─────────────────────────────────────────────────────

    @property
    def has_chat_id(self) -> bool:
        """Return True if a Telegram chat_id has been registered."""
        return self._get_chat_id() is not None

    @property
    def bot_token_configured(self) -> bool:
        """Return True if the Telegram bot token is set."""
        return bool(self._bot_token)
