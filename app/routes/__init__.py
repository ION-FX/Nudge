from __future__ import annotations

from . import classes, assignments, auth, main, materials, tutor

ALL_ROUTERS = [r.router for r in (main, auth, classes, materials, assignments, tutor)]
