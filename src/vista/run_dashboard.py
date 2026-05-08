#!/usr/bin/env python3
"""
VISTA Dashboard — Quick Start
==============================
Run this from the vista/ directory to start the web dashboard.

    python run_dashboard.py

Or with environment override:

    DEMO_MODE=true python run_dashboard.py
    FLASK_SECRET_KEY=my-secret python run_dashboard.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure vista/ is on the path
vista_root = Path(__file__).resolve().parent
sys.path.insert(0, str(vista_root))

# Load .env if present (dotenv is optional)
try:
    from dotenv import load_dotenv
    env_path = vista_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[vista] Loaded environment from {env_path}")
except ImportError:
    pass

# Default demo mode unless explicitly disabled
if "DEMO_MODE" not in os.environ:
    os.environ["DEMO_MODE"] = "true"
    print("[vista] DEMO_MODE=true (set DEMO_MODE=false to use real hardware)")

from dashboard import create_app, start

app = create_app()

print("=" * 50)
print("  VISTA Dashboard")
print("  Open http://localhost:5000 in your browser")
print("  (or http://<raspberry-pi-ip>:5000 from phone)")
print("=" * 50)

start(host="0.0.0.0", port=5000)
