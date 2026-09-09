from __future__ import annotations

from . import assignments, auth, classes, main, materials, setup, tutor

ALL_ROUTERS = [r.router for r in (setup, main, auth, classes, materials, assignments, tutor)]
