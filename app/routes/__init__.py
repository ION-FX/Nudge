from __future__ import annotations

from . import (
    announcements,
    assignments,
    auth,
    classes,
    gradebook,
    main,
    materials,
    notifications,
    profile,
    quizzes,
    search,
    setup,
    tutor,
)

ALL_ROUTERS = [
    r.router
    for r in (
        setup,
        main,
        auth,
        classes,
        materials,
        assignments,
        announcements,
        quizzes,
        notifications,
        profile,
        gradebook,
        search,
        tutor,
    )
]
