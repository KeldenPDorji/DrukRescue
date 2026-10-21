"""Turn events into human-readable notifications. Pure functions: event in, list of drafts out."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Draft:
    title: str
    message: str
    kind: str
    user_id: str | None = None
    role: str | None = None
    incident_id: str | None = None
    district: str | None = None
    severity: str | None = None

    @property
    def recipient_key(self) -> str:
        if self.user_id:
            return f"user:{self.user_id}"
        return f"role:{self.role}" if self.role else "all"


def _place(d: dict) -> str:
    return d.get("location_name") or d.get("district") or "your area"


def _type(d: dict) -> str:
    return (d.get("type") or d.get("incident_type") or "incident").replace("_", " ").title()


STATUS_TEXT = {
    "VERIFIED": "has been verified. We are finding the nearest team.",
    "IN_PROGRESS": "- the rescue team is on scene.",
    "RESOLVED": "has been resolved. Stay safe.",
    "CANCELLED": "was cancelled.",
}
STAGE_TEXT = {
    "ACCEPTED": "The rescue team has accepted your case.",
    "EN_ROUTE": "The rescue team is on the way.",
}


def drafts_for(event_type: str, d: dict) -> list[Draft]:
    if event_type == "incident.created":
        code = d.get("id")
        return [
            Draft("Report received", f"Your report {code} was received. Help is being arranged.", "INCIDENT",
                  user_id=d.get("reporter_id"), incident_id=code, district=d.get("district")),
            Draft(f"New {_type(d)} report", f"{code}: {_type(d)} reported near {_place(d)} ({d.get('severity')}).",
                  "INCIDENT", role="ADMIN", incident_id=code, district=d.get("district"), severity=d.get("severity")),
        ]

    if event_type == "incident.status_changed":
        code, stage, new = d.get("id"), d.get("stage"), d.get("status")
        if stage in STAGE_TEXT:
            text = STAGE_TEXT[stage]
        elif new in STATUS_TEXT and new != d.get("from_status"):
            text = f"Your report {code} {STATUS_TEXT[new]}"
        else:
            return []  # e.g. DISPATCHED: dispatch.assigned sends a richer message
        return [Draft(f"Update on {code}", text, "INCIDENT", user_id=d.get("reporter_id"), incident_id=code,
                      district=d.get("district"))]

    if event_type == "dispatch.assigned":
        code = d.get("incident_id")
        eta = f" ETA about {round(d['eta_minutes'])} min." if d.get("eta_minutes") else ""
        team = d.get("team") or d.get("responder_name") or "A rescue team"
        drafts = [
            Draft("Rescue team dispatched", f"{team} is coming with {d.get('vehicle_name')}.{eta}", "DISPATCH",
                  user_id=d.get("reporter_id"), incident_id=code, district=d.get("district")),
        ]
        if d.get("responder_user_id"):
            drafts.append(Draft("New assignment", f"{code}: {_type(d)} near {_place(d)}. Vehicle {d.get('vehicle_name')}.",
                                "DISPATCH", user_id=d["responder_user_id"], incident_id=code, district=d.get("district"),
                                severity=d.get("severity")))
        return drafts

    if event_type == "alert.issued":
        where = f" ({d['district']})" if d.get("district") else ""
        return [Draft(f"{d.get('title', 'Alert')}{where}", d.get("message", ""), "ALERT",
                      district=d.get("district"), severity=d.get("severity"))]

    return []
