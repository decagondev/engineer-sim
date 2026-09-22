"""Module-level names shared by sim/adapters/web/app.py and its route modules."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("sim.adapters.web.app")

_STATIC = Path(__file__).parent / "static"
