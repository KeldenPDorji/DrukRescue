# Shelter service (scaffold, task **B2**)

Evacuation shelters and how full they are. Citizens use it to find the nearest shelter with free space.

The scaffold already boots, serves `/healthz`, `/readyz` and `/metrics`, connects to its own `shelter`
schema, and has a Helm chart, an ArgoCD app and a compose entry. You write the domain logic.

## Data model (suggested)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | str(120) | e.g. "Babesa Higher Secondary School" |
| district | str(64) | |
| lat, lng | float | |
| capacity | int | ≥ 0 |
| occupied | int | 0 ≤ occupied ≤ capacity |
| contact_phone | str(32), nullable | |
| is_open | bool | default true |
| updated_at | timestamptz | |

## Endpoints

Through the gateway these become `/api/shelters/...`. The gateway already restricts POST/PATCH/DELETE to `ADMIN`.
Enforce it in the service too, using `require_roles(Role.ADMIN)`.

| Method | Path | Who | Behaviour |
|---|---|---|---|
| GET | `/shelters?district=&open_only=` | any user | list |
| GET | `/shelters/nearby?lat=&lng=&limit=5` | any user | open shelters with free space, nearest first, each with `distance_km` and `free` |
| GET | `/shelters/{id}` | any user | one shelter, 404 if missing |
| POST | `/shelters` | ADMIN | create, 201 |
| PATCH | `/shelters/{id}` | ADMIN | update; 422/409 if `occupied > capacity` |
| DELETE | `/shelters/{id}` | ADMIN | 204 |

For `nearby`, call the Location service the same way Dispatch does (`services/dispatch/app/main.py → rank()`):
`service_client("location").post("/location/nearest", json={"origin": {...}, "units": [...]})`.
Also add `shelter` to `networkPolicy.allowFrom` in `deploy/charts/location/values.yaml`, so the NetworkPolicy
lets the shelter pods reach Location.

## Done when

- [ ] All endpoints work, with tests in `tests/` (happy path, validation, 403 for citizens on writes, 404s)
- [ ] `nearby` excludes closed and full shelters
- [ ] `scripts/seed.py` seeds a few shelters (uncomment the shelter block)
- [ ] The citizen page in the frontend shows the 3 nearest shelters (coordinate with B3)
- [ ] Optional: a `drukrescue_shelter_free_beds{district}` gauge (see `register_scrape_time_gauge` in Responder)
