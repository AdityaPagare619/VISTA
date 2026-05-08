"""
VISTA Cloud Vision — Gemini Vision API Client
==============================================
Sends camera frames to Google Gemini for AI-powered scene analysis
and crash-scene assessment.  Returns structured JSON results parsed
into Python dictionaries.

Graceful degradation: if the API call fails (network, auth, rate-limit),
returns ``{"error": "message", "scene_type": "unknown", "safety_rating": 0}``
so the decision engine can continue with other sensor modalities.

Environment
    Requires ``GEMINI_API_KEY`` set in ``.env`` (loaded automatically
    via ``python-dotenv`` at module import).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from loguru import logger

# ── Load env vars at module level ────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        logger.debug(f"Loaded environment from {_env_path}")
except ImportError:
    logger.debug("python-dotenv not installed — relying on system env vars")


class CloudVision:
    """Gemini Vision API wrapper for vehicle scene analysis.

    Supports both general scene analysis (``analyze_scene``) and
    focused crash-scene analysis (``analyze_crash_scene``).

    All methods return a dict — never raise exceptions to the caller.
    On failure, the dict contains an ``"error"`` key.

    Usage::

        cv = CloudVision()
        result = cv.analyze_scene(jpeg_bytes)
        # → {"scene_type": "highway", "hazard_score": 5, ...}

        crash_report = cv.analyze_crash_scene(jpeg_bytes)
        # → "The image shows a frontal collision..."
    """

    # ── Prompt templates (sent to Gemini) ────────────────────────
    _SCENE_PROMPT = (
        "You are an automotive safety AI. Analyze this image taken from a vehicle "
        "dashboard camera. Return a JSON object with these exact keys:\n"
        '  "scene_type": one of [highway, city_street, rural_road, parking_lot, '
        "residential, off_road, tunnel, bridge, unknown],\n"
        '  "vehicles": number of vehicles visible (integer),\n'
        '  "hazards": list of hazard strings (e.g. [\"pedestrian\", \"debris\", '
        "\"animal\", \"stopped_vehicle\"]), or empty list if none,\n"
        '  "road_condition": one of [dry, wet, snow, ice, gravel, unknown],\n'
        '  "safety_rating": integer from 0 (extremely hazardous) to 100 (perfectly safe),\n'
        '  "hazard_score": integer from 0 (no hazard) to 100 (imminent danger),\n'
        '  "description": a one-sentence summary of the scene.\n'
        "Return ONLY valid JSON, no markdown, no code fences."
    )

    _CRASH_PROMPT = (
        "You are a crash scene investigator AI. Analyze this image from a vehicle "
        "that may have been involved in a collision. Describe:\n"
        "- What type of collision appears to have occurred (frontal, rear, side, rollover, none)\n"
        "- Severity assessment (minor, moderate, severe, critical)\n"
        "- Visible damage to the vehicle(s)\n"
        "- Any hazards at the scene (fire, smoke, fluids, debris)\n"
        "- Whether emergency services should be contacted\n"
        "- Recommended immediate actions\n\n"
        "Provide a concise, structured report in plain English. "
        "Do NOT use markdown formatting."
    )

    def __init__(self) -> None:
        cfg = self._load_config()
        cloud_cfg = cfg.get("cloud", {}).get("vision", {})

        self._provider: str = cloud_cfg.get("provider", "gemini")
        self._model: str = cloud_cfg.get("model", "gemini-1.5-flash")
        api_key_env: str = cloud_cfg.get("api_key_env", "GEMINI_API_KEY")
        self._max_retries: int = int(cloud_cfg.get("max_retries", 3))
        self._timeout: int = int(cloud_cfg.get("timeout_seconds", 10))

        self._api_key: str = os.environ.get(api_key_env, "")
        self._client: Any = None  # genai.GenerativeModel

        if not self._api_key:
            logger.error(
                f"CloudVision: {api_key_env} not set in environment. "
                f"All calls will return error dicts."
            )
        else:
            logger.debug(
                f"CloudVision: API key found ({api_key_env[:4]}...{api_key_env[-4:]})"
            )
            self._init_client()

        logger.info(
            f"CloudVision initialized | provider={self._provider} "
            f"model={self._model} | retries={self._max_retries} timeout={self._timeout}s"
        )

    # ── Config loader ────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    # ── Client initialisation ────────────────────────────────────

    def _init_client(self) -> None:
        """Configure the Gemini SDK client."""
        try:
            import google.generativeai as genai  # type: ignore[import-untyped]

            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._model)
            logger.success(f"Gemini client initialised | model={self._model}")

        except ImportError:
            logger.error(
                "google-generativeai not installed — CloudVision unavailable"
            )
            self._client = None
        except Exception as exc:
            logger.error(f"Failed to initialise Gemini client: {exc}")
            self._client = None

    # ══════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════

    def analyze_scene(self, image_bytes: bytes) -> Dict[str, Any]:
        """Analyse a general driving scene image.

        Args:
            image_bytes: JPEG or PNG image as raw bytes.

        Returns:
            Dict with keys: ``scene_type``, ``vehicles``, ``hazards``,
            ``road_condition``, ``safety_rating``, ``hazard_score``,
            ``description``.  On error, also contains ``"error"`` key.

            Fallback default on total failure:
            ``{"scene_type": "unknown", "hazard_score": 0, "safety_rating": 50, "error": "..."}``.
        """
        if not self._api_key or self._client is None:
            return self._error_result("CloudVision client not initialised (API key missing?)")

        try:
            # Build the multimodal request
            image_part = {"mime_type": "image/jpeg", "data": image_bytes}
            response = self._call_with_retry(
                prompt=self._SCENE_PROMPT,
                image=image_part,
            )

            if response is None:
                return self._error_result("No response from Gemini API after retries")

            parsed = self._parse_json(response)
            return self._validate_scene_result(parsed)

        except Exception as exc:
            logger.error(f"analyze_scene failed: {exc}")
            return self._error_result(str(exc))

    def analyze_crash_scene(self, image_bytes: bytes) -> str:
        """Analyse a potential crash scene image in detail.

        Args:
            image_bytes: JPEG or PNG image as raw bytes.

        Returns:
            A detailed crash analysis report as plain text.
            On error, returns ``"Error: <message>"``.
        """
        if not self._api_key or self._client is None:
            return "Error: CloudVision client not initialised (API key missing?)"

        try:
            image_part = {"mime_type": "image/jpeg", "data": image_bytes}
            response = self._call_with_retry(
                prompt=self._CRASH_PROMPT,
                image=image_part,
            )

            if response is None:
                return "Error: No response from Gemini API after retries"

            return str(response).strip()

        except Exception as exc:
            logger.error(f"analyze_crash_scene failed: {exc}")
            return f"Error: {exc}"

    # ══════════════════════════════════════════════════════════════
    # Internal: API calling
    # ══════════════════════════════════════════════════════════════

    def _call_with_retry(
        self, prompt: str, image: Dict[str, Any]
    ) -> Optional[str]:
        """Call Gemini with exponential backoff retry.

        Returns the response text on success, ``None`` on total failure.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                # Build content: [prompt, image]
                contents = [prompt, image]

                # Call Gemini
                result = self._client.generate_content(
                    contents=contents,
                    generation_config={
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "top_k": 40,
                    },
                    request_options={"timeout": self._timeout * 1000},  # ms
                )

                if result and result.text:
                    return result.text

                # Empty response
                logger.warning(
                    f"Gemini returned empty response (attempt {attempt}/{self._max_retries})"
                )
                last_error = ValueError("Empty response from Gemini")

            except Exception as exc:
                logger.warning(
                    f"Gemini API call failed (attempt {attempt}/{self._max_retries}): {exc}"
                )
                last_error = exc

                # Don't retry on auth errors
                error_str = str(exc).lower()
                if any(kw in error_str for kw in ("401", "403", "unauthorized", "invalid key")):
                    logger.error(f"Auth error — not retrying: {exc}")
                    return None

            # Exponential backoff
            if attempt < self._max_retries:
                delay = 2.0 ** (attempt - 1)
                logger.debug(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)

        if last_error:
            logger.error(f"All {self._max_retries} Gemini retries exhausted: {last_error}")
        return None

    # ══════════════════════════════════════════════════════════════
    # Internal: Response parsing
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """Extract and parse a JSON object from Gemini's text response.

        Handles various quirks: markdown code fences, extra whitespace,
        trailing commas.
        """
        text = text.strip()

        # Remove markdown code fences if present
        fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(fence_pattern, text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # Find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]

        # Remove trailing commas before } or ]
        text = re.sub(r",(\s*[}\]])", r"\1", text)

        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON parse failed: {exc} — response: {text[:200]}")
            return {}

    @staticmethod
    def _validate_scene_result(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the parsed result has all expected keys with sensible defaults."""
        return {
            "scene_type": str(raw.get("scene_type", "unknown")),
            "vehicles": int(raw.get("vehicles", 0)),
            "hazards": raw.get("hazards", []) if isinstance(raw.get("hazards"), list) else [],
            "road_condition": str(raw.get("road_condition", "unknown")),
            "safety_rating": int(raw.get("safety_rating", 50)),
            "hazard_score": int(raw.get("hazard_score", 0)),
            "description": str(raw.get("description", "No description available.")),
        }

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        """Return a safe fallback dict when the API call fails."""
        return {
            "scene_type": "unknown",
            "vehicles": 0,
            "hazards": [],
            "road_condition": "unknown",
            "safety_rating": 50,
            "hazard_score": 0,
            "description": f"Error: {message}",
            "error": message,
        }
