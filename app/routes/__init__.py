from __future__ import annotations

from . import (
    ai_admin,
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
        ai_admin,
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
