# Resource service (scaffold, task **D1**)

Relief supply levels per district warehouse, so the command centre can see what's running low.

## Data model (suggested)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| item | enum | `MEDICAL_KIT`, `BLANKET`, `WATER`, `FOOD`, `TENT`, `OTHER` |
| district | str(64) | where the stock is held |
| quantity | int | never negative |
| unit | str(16) | "kits", "litres", "packs", ... |
| low_stock_threshold | int | |
| updated_at | timestamptz | |

Unique on `(item, district)`.

## Endpoints (gateway: `/api/resources/...`; writes are ADMIN-only)

| Method | Path | Who | Behaviour |
|---|---|---|---|
| GET | `/resources?district=&item=` | any user | list |
| GET | `/resources/low-stock` | any user | rows where `quantity <= low_stock_threshold` |
| POST | `/resources` | ADMIN | create, 201; 409 on duplicate `(item, district)` |
| PATCH | `/resources/{id}` | ADMIN | change threshold/unit |
| POST | `/resources/{id}/adjust` | ADMIN | body `{delta: int, reason: str}`; 409 if it would go below 0 |

Make `adjust` safe under concurrency with a conditional UPDATE (same idea as `claim` in
`services/responder/app/main.py`): `UPDATE ... SET quantity = quantity + :delta WHERE id = :id AND quantity + :delta >= 0`.

## Done when

- [ ] Endpoints and tests written (including the "never below zero" case)
- [ ] Seed data in `scripts/seed.py`
- [ ] A `drukrescue_resource_quantity{item,district}` gauge for the Command Centre dashboard
- [ ] Optional: publish `resource.low_stock` and have Notification alert admins (update `docs/events.md`)
