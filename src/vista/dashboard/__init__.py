"""
VISTA Web Dashboard
===================
Flask-based real-time telemetry dashboard for the VISTA platform.

Provides a browser-accessible live view of vehicle sensor data,
alert history, and system status.  Uses Flask-SocketIO for
push-based updates — no page reload required.

Exports:
    create_app  — Flask application factory
    start       — Initialise sensors and begin serving
    stop        — Graceful shutdown
"""

from __future__ import annotations

from .app import create_app, start, stop

__all__ = ["create_app", "start", "stop"]
