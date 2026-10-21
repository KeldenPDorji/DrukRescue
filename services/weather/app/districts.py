"""Approximate coordinates of dzongkhag headquarters (lat, lng)."""

DISTRICTS: dict[str, tuple[float, float]] = {
    "thimphu": (27.4728, 89.6390),
    "paro": (27.4305, 89.4133),
    "punakha": (27.5916, 89.8774),
    # TODO(D2): add the remaining 17 dzongkhags.
}
