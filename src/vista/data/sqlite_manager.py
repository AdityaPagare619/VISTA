"""
VISTA SQLite Event Database
===========================
Local persistent storage for events, daily reports, and audit logs.
Thread-safe with connection-per-thread pattern.

Tables:
    events       — All detected events (crash, theft, harsh_braking, etc.)
    daily_reports— Aggregated daily driving summaries
    audit_log    — Security-relevant actions (arm/disarm, config changes)

Uses stdlib ``sqlite3`` — no extra dependencies.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from . import _is_demo_mode, _load_config


class SQLiteManager:
    """Thread-safe SQLite database for VISTA event storage.

    Each thread gets its own connection (sqlite3 doesn't support
    sharing connections across threads). All methods are safe to
    call from any thread.

    Usage::

        db = SQLiteManager()
        db.init_db()
        db.log_event("crash", 0.85, "critical", {"imu_jerk": 0.9})
        events = db.get_recent_events(10)
    """

    def __init__(self) -> None:
        cfg = _load_config()
        sqlite_cfg = cfg.get("storage", {}).get("sqlite", {})
        device_cfg = cfg.get("device", {})

        self._device_id: str = device_cfg.get("id", "VISTA-0001")
        self._demo_mode = _is_demo_mode()

        # Database path (v3.0: prefer USB SSD, fallback to local)
        storage_cfg = cfg.get("storage", {})
        sqlite_cfg = storage_cfg.get("sqlite", {})
        ssd_mount = storage_cfg.get("data_mount", "/mnt/vista-data")
        ssd_path = Path(ssd_mount) / "events.db"
        fallback_path = sqlite_cfg.get("fallback_path", "data/events.db")
        primary_path = sqlite_cfg.get("path", str(ssd_path))

        # Try SSD mount first, then fallback
        self._db_path = Path(primary_path)
        if not self._db_path.parent.exists():
            # SSD not mounted — use local fallback
            self._db_path = Path(fallback_path)
            if not self._db_path.is_absolute():
                package_root = Path(__file__).resolve().parent.parent
                self._db_path = package_root / self._db_path
            logger.warning(
                f"USB SSD not mounted at {ssd_mount} — "
                f"using local fallback: {self._db_path}"
            )
        elif not self._db_path.is_absolute():
            package_root = Path(__file__).resolve().parent.parent
            self._db_path = package_root / self._db_path

        # Thread-local connections
        self._local = threading.local()
        self._initialized = False
        self._init_lock = threading.Lock()

        logger.info(
            f"SQLiteManager initialized | path={self._db_path} | "
            f"demo={self._demo_mode}"
        )

    # ── Initialization ─────────────────────────────────────────────

    def init_db(self) -> bool:
        """Create tables and indexes if they don't exist.

        Idempotent — safe to call multiple times.
        Returns True on success.
        """
        if self._initialized:
            return True

        with self._init_lock:
            if self._initialized:
                return True

            try:
                # Ensure directory exists
                self._db_path.parent.mkdir(parents=True, exist_ok=True)

                conn = self._get_connection()
                cursor = conn.cursor()

                # ── Events Table ──────────────────────────────────
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        confidence REAL NOT NULL DEFAULT 0.0,
                        severity TEXT NOT NULL DEFAULT 'info',
                        evidence TEXT NOT NULL DEFAULT '{}',
                        image_path TEXT,
                        location TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        notes TEXT,
                        device_id TEXT NOT NULL
                    )
                """)

                # ── Daily Reports Table ───────────────────────────
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS daily_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL UNIQUE,
                        total_distance_km REAL DEFAULT 0.0,
                        total_drive_time_s REAL DEFAULT 0.0,
                        max_speed_kmh REAL DEFAULT 0.0,
                        avg_speed_kmh REAL DEFAULT 0.0,
                        fuel_used_l REAL DEFAULT 0.0,
                        harsh_braking_count INTEGER DEFAULT 0,
                        rapid_accel_count INTEGER DEFAULT 0,
                        sharp_turn_count INTEGER DEFAULT 0,
                        overspeed_count INTEGER DEFAULT 0,
                        total_events INTEGER DEFAULT 0,
                        driver_score REAL DEFAULT 100.0,
                        summary TEXT,
                        device_id TEXT NOT NULL
                    )
                """)

                # ── Audit Log Table ───────────────────────────────
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        action TEXT NOT NULL,
                        details TEXT DEFAULT '{}',
                        source TEXT DEFAULT 'system',
                        device_id TEXT NOT NULL
                    )
                """)

                # ── Indexes ───────────────────────────────────────
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_timestamp
                    ON events(timestamp)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_type
                    ON events(event_type)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_severity
                    ON events(severity)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_daily_reports_date
                    ON daily_reports(date)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                    ON audit_log(timestamp)
                """)

                conn.commit()
                self._initialized = True
                logger.success(
                    f"SQLite database initialized | "
                    f"tables=events,daily_reports,audit_log"
                )
                return True

            except Exception as exc:
                logger.error(f"SQLite init_db failed: {exc}")
                return False

    # ── Connection Management ──────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local database connection.

        Each thread gets its own connection (sqlite3 requirement).
        Connections are cached in thread-local storage.
        """
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self._db_path),
                timeout=10.0,          # Wait up to 10s for locks
                isolation_level=None,   # Manual transactions
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent reads
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.connection = conn
            logger.debug(
                f"SQLite connection created for thread {threading.current_thread().name}"
            )

        return self._local.connection

    # ── Event Logging ──────────────────────────────────────────────

    def log_event(
        self,
        event_type: str,
        confidence: float,
        severity: str = "info",
        evidence: Optional[Dict[str, Any]] = None,
        image_path: Optional[str] = None,
        location: Optional[Dict[str, float]] = None,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Log a new event to the database.

        Args:
            event_type: Type of event (crash, theft, harsh_braking, etc.).
            confidence: Confidence score (0.0-1.0).
            severity: "critical", "warning", or "info".
            evidence: Dict of sensor evidence (e.g., {"imu_jerk": 0.85}).
            image_path: Optional path to captured image.
            location: Optional GPS dict {"lat", "lon", "speed", "accuracy"}.
            notes: Optional human-readable notes.

        Returns:
            The new event ID, or None on failure.
        """
        if not self._initialized:
            if not self.init_db():
                return None

        # Validate
        if not event_type or not isinstance(event_type, str):
            logger.error("log_event: event_type must be a non-empty string")
            return None

        confidence = max(0.0, min(1.0, float(confidence)))
        timestamp = time.time()

        evidence_json = json.dumps(evidence or {}, ensure_ascii=False)
        location_json = json.dumps(location, ensure_ascii=False) if location else None

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """INSERT INTO events
                   (timestamp, event_type, confidence, severity, evidence,
                    image_path, location, status, notes, device_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (
                    timestamp,
                    event_type,
                    confidence,
                    severity,
                    evidence_json,
                    image_path,
                    location_json,
                    notes,
                    self._device_id,
                ),
            )
            conn.commit()
            event_id = cursor.lastrowid

            logger.info(
                f"Event logged | id={event_id} | type={event_type} | "
                f"severity={severity} | confidence={confidence:.1%}"
            )

            # Also update daily report counters
            self._update_daily_counters(event_type)

            return event_id

        except Exception as exc:
            logger.error(f"SQLite log_event failed: {exc}")
            return None

    # ── Query Methods ──────────────────────────────────────────────

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent events, newest first.

        Args:
            limit: Maximum number of events to return.

        Returns:
            List of event dicts, each with parsed evidence and location.
        """
        if not self._initialized:
            if not self.init_db():
                return []

        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT * FROM events
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            return [self._row_to_dict(row) for row in rows]

        except Exception as exc:
            logger.error(f"SQLite get_recent_events failed: {exc}")
            return []

    def get_events_by_type(
        self, event_type: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return events of a specific type, newest first.

        Args:
            event_type: Event type to filter by.
            limit: Maximum number of events to return.

        Returns:
            List of event dicts.
        """
        if not self._initialized:
            if not self.init_db():
                return []

        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT * FROM events
                   WHERE event_type = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (event_type, limit),
            ).fetchall()

            return [self._row_to_dict(row) for row in rows]

        except Exception as exc:
            logger.error(f"SQLite get_events_by_type failed: {exc}")
            return []

    def get_events_since(
        self, since_timestamp: float, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return events after a given timestamp.

        Args:
            since_timestamp: Unix epoch timestamp (exclusive).
            limit: Maximum number of events.

        Returns:
            List of event dicts.
        """
        if not self._initialized:
            if not self.init_db():
                return []

        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT * FROM events
                   WHERE timestamp > ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (since_timestamp, limit),
            ).fetchall()

            return [self._row_to_dict(row) for row in rows]

        except Exception as exc:
            logger.error(f"SQLite get_events_since failed: {exc}")
            return []

    def get_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Return a single event by its ID, or None if not found."""
        if not self._initialized:
            if not self.init_db():
                return None

        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()

            if row is None:
                return None
            return self._row_to_dict(row)

        except Exception as exc:
            logger.error(f"SQLite get_event_by_id failed: {exc}")
            return None

    def update_event_status(
        self, event_id: int, status: str, notes: Optional[str] = None
    ) -> bool:
        """Update the status of an event (e.g., 'active' → 'resolved').

        Returns:
            True if at least one row was updated.
        """
        if not self._initialized:
            if not self.init_db():
                return False

        valid_statuses = {"active", "acknowledged", "resolved", "false_alarm"}
        if status not in valid_statuses:
            logger.warning(f"Unknown event status: '{status}'")
            return False

        try:
            conn = self._get_connection()
            if notes:
                cursor = conn.execute(
                    "UPDATE events SET status = ?, notes = ? WHERE id = ?",
                    (status, notes, event_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE events SET status = ? WHERE id = ?",
                    (status, event_id),
                )
            conn.commit()
            return cursor.rowcount > 0

        except Exception as exc:
            logger.error(f"SQLite update_event_status failed: {exc}")
            return False

    # ── Audit Log ──────────────────────────────────────────────────

    def log_audit(
        self,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> Optional[int]:
        """Log a security-relevant action to the audit log.

        Args:
            action: Description of the action (e.g., "arm", "disarm").
            details: Optional contextual details.
            source: Source of the action ("system", "ble", "mqtt", "telegram").

        Returns:
            The new audit entry ID, or None on failure.
        """
        if not self._initialized:
            if not self.init_db():
                return None

        try:
            conn = self._get_connection()
            details_json = json.dumps(details or {}, ensure_ascii=False)
            cursor = conn.execute(
                """INSERT INTO audit_log
                   (timestamp, action, details, source, device_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (time.time(), action, details_json, source, self._device_id),
            )
            conn.commit()
            return cursor.lastrowid

        except Exception as exc:
            logger.error(f"SQLite audit log failed: {exc}")
            return None

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent audit log entries, newest first."""
        if not self._initialized:
            if not self.init_db():
                return []

        try:
            conn = self._get_connection()
            rows = conn.execute(
                """SELECT * FROM audit_log
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            return [self._row_to_dict(row) for row in rows]

        except Exception as exc:
            logger.error(f"SQLite get_audit_log failed: {exc}")
            return []

    # ── Daily Reports ──────────────────────────────────────────────

    def _update_daily_counters(self, event_type: str) -> None:
        """Increment relevant daily counters based on event type.

        Called internally after every log_event().
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            conn = self._get_connection()

            # Ensure today's report exists
            conn.execute(
                """INSERT OR IGNORE INTO daily_reports
                   (date, device_id) VALUES (?, ?)""",
                (today, self._device_id),
            )

            # Map event types to counter columns
            counter_map = {
                "harsh_braking": "harsh_braking_count",
                "rapid_accel": "rapid_accel_count",
                "sharp_turn": "sharp_turn_count",
                "overspeed": "overspeed_count",
            }

            if event_type in counter_map:
                column = counter_map[event_type]
                conn.execute(
                    f"""UPDATE daily_reports
                        SET {column} = {column} + 1,
                            total_events = total_events + 1
                        WHERE date = ?""",
                    (today,),
                )

            # Always increment total events
            conn.execute(
                """UPDATE daily_reports
                   SET total_events = total_events + 1
                   WHERE date = ?""",
                (today,),
            )

            conn.commit()

        except Exception as exc:
            logger.warning(f"Daily counter update failed: {exc}")

    def get_daily_report(
        self, date_str: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Return the daily report for a specific date, or today.

        Args:
            date_str: Date in "YYYY-MM-DD" format, or None for today.
        """
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not self._initialized:
            if not self.init_db():
                return None

        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE date = ?",
                (date_str,),
            ).fetchone()

            if row is None:
                return None
            return self._row_to_dict(row)

        except Exception as exc:
            logger.error(f"SQLite get_daily_report failed: {exc}")
            return None

    def update_daily_report(
        self,
        date_str: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Update fields in a daily report.

        Args:
            date_str: Date in "YYYY-MM-DD" format, or None for today.
            **kwargs: Field names and values to update (e.g., total_distance_km=42.5).
        """
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not kwargs:
            return True

        if not self._initialized:
            if not self.init_db():
                return False

        try:
            conn = self._get_connection()

            # Ensure report exists
            conn.execute(
                """INSERT OR IGNORE INTO daily_reports
                   (date, device_id) VALUES (?, ?)""",
                (date_str, self._device_id),
            )

            # Build SET clause
            set_parts = []
            values = []
            allowed_fields = {
                "total_distance_km", "total_drive_time_s", "max_speed_kmh",
                "avg_speed_kmh", "fuel_used_l", "harsh_braking_count",
                "rapid_accel_count", "sharp_turn_count", "overspeed_count",
                "total_events", "driver_score", "summary",
            }

            for field, value in kwargs.items():
                if field in allowed_fields:
                    set_parts.append(f"{field} = ?")
                    values.append(value)

            if not set_parts:
                return True

            values.append(date_str)
            query = f"UPDATE daily_reports SET {', '.join(set_parts)} WHERE date = ?"
            conn.execute(query, values)
            conn.commit()
            return True

        except Exception as exc:
            logger.error(f"SQLite update_daily_report failed: {exc}")
            return False

    # ── Utilities ──────────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict with parsed JSON fields."""
        data = dict(row)

        # Parse JSON fields if they are strings
        for field in ("evidence", "details"):
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep as string if not valid JSON

        if "location" in data and isinstance(data["location"], str):
            try:
                data["location"] = json.loads(data["location"])
            except (json.JSONDecodeError, TypeError):
                pass

        return data

    def get_stats(self) -> Dict[str, Any]:
        """Return database statistics (total events, by type, by severity)."""
        if not self._initialized:
            if not self.init_db():
                return {}

        try:
            conn = self._get_connection()

            total_events = conn.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

            by_type = {}
            for row in conn.execute(
                """SELECT event_type, COUNT(*) as cnt
                   FROM events GROUP BY event_type"""
            ).fetchall():
                by_type[row["event_type"]] = row["cnt"]

            by_severity = {}
            for row in conn.execute(
                """SELECT severity, COUNT(*) as cnt
                   FROM events GROUP BY severity"""
            ).fetchall():
                by_severity[row["severity"]] = row["cnt"]

            total_audit = conn.execute(
                "SELECT COUNT(*) FROM audit_log"
            ).fetchone()[0]

            db_size_mb = self._db_path.stat().st_size / (1024 * 1024) \
                if self._db_path.exists() else 0.0

            return {
                "total_events": total_events,
                "events_by_type": by_type,
                "events_by_severity": by_severity,
                "total_audit_entries": total_audit,
                "db_size_mb": round(db_size_mb, 2),
                "db_path": str(self._db_path),
            }

        except Exception as exc:
            logger.error(f"SQLite get_stats failed: {exc}")
            return {}

    def close(self) -> None:
        """Close the thread-local connection, if any."""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            try:
                self._local.connection.close()
                logger.debug("SQLite connection closed")
            except Exception as exc:
                logger.warning(f"Error closing SQLite connection: {exc}")
            self._local.connection = None
