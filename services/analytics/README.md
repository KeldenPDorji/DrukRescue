# Analytics service (scaffold, task **D3**)

Builds its own read model from events. It never queries another service's database
(that's the "own data" rule), and serves statistics to the command centre.

## Data model (suggested)

`incident_facts`: one row per incident, upserted as events arrive.

| Column | From event |
|---|---|
| incident_id (PK) | `incident.created` → `data.id` |
| type, severity, district | `incident.created` |
| status | latest `incident.status_changed` → `data.status` |
| reported_at | `incident.created` → `data.created_at` |
| dispatched_at, time_to_dispatch_seconds | `dispatch.assigned` |
| resolved_at | `incident.status_changed` with status RESOLVED/CANCELLED |

Events can arrive **out of order or twice**. Upsert by `incident_id` and only move timestamps forward.

## Endpoint (gateway: `/api/analytics/...`, ADMIN only)

`GET /analytics/stats?since=<ISO datetime>` returns:

```json
{
  "total": 104,
  "by_type": {"FLOOD": 60, "LANDSLIDE": 30, "FIRE": 14},
  "by_status": {"RESOLVED": 80, "DISPATCHED": 20, "VERIFIED": 4},
  "by_district": {"Thimphu": 70, "Paro": 34},
  "avg_time_to_dispatch_seconds": 41.2,
  "p95_time_to_dispatch_seconds": 120.5
}
```

## Done when

- [ ] Consumer stores facts idempotently (test: deliver the same event twice, see `bus.deliver` in the Incident tests)
- [ ] `/analytics/stats` returns the shape above, with tests
- [ ] The admin page in the frontend shows the stats (coordinate with B3)
