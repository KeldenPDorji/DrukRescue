"""The incident lifecycle: REPORTED -> VERIFIED -> DISPATCHED -> IN_PROGRESS -> RESOLVED (+ CANCELLED).

Kept as pure data/functions so it is easy to test and to explain.
"""

from __future__ import annotations

from enum import StrEnum


class IncidentType(StrEnum):
    FLOOD = "FLOOD"
    GLOF = "GLOF"  # glacial lake outburst flood
    LANDSLIDE = "LANDSLIDE"
    EARTHQUAKE = "EARTHQUAKE"
    FIRE = "FIRE"
    ACCIDENT = "ACCIDENT"
    MEDICAL = "MEDICAL"
    OTHER = "OTHER"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Status(StrEnum):
    REPORTED = "REPORTED"
    VERIFIED = "VERIFIED"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class Stage(StrEnum):
    """What a responder taps in the app. Stages map onto statuses (see STAGE_RULES)."""

    ACCEPTED = "ACCEPTED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    RESOLVED = "RESOLVED"


TRANSITIONS: dict[Status, set[Status]] = {
    Status.REPORTED: {Status.VERIFIED, Status.CANCELLED},
    Status.VERIFIED: {Status.DISPATCHED, Status.CANCELLED},
    Status.DISPATCHED: {Status.IN_PROGRESS, Status.CANCELLED},
    Status.IN_PROGRESS: {Status.RESOLVED},
    Status.RESOLVED: set(),
    Status.CANCELLED: set(),
}

TERMINAL = {Status.RESOLVED, Status.CANCELLED}
ACTIVE = set(Status) - TERMINAL

# stage -> (status the incident must be in, status it moves to)
STAGE_RULES: dict[Stage, tuple[Status, Status]] = {
    Stage.ACCEPTED: (Status.DISPATCHED, Status.DISPATCHED),
    Stage.EN_ROUTE: (Status.DISPATCHED, Status.DISPATCHED),
    Stage.ON_SCENE: (Status.DISPATCHED, Status.IN_PROGRESS),
    Stage.RESOLVED: (Status.IN_PROGRESS, Status.RESOLVED),
}


def can_transition(current: Status | str, target: Status | str) -> bool:
    return Status(target) in TRANSITIONS[Status(current)]
