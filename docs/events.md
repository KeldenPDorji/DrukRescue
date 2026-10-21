# Event contracts

Services talk asynchronously through **one topic exchange**, `drukrescue.events`, plus **one work queue**,
`dispatch.requests`. This file is the contract: if you change a payload, update it here in the same PR
and check every consumer listed.

## Envelope

Every message body looks like this (`libs/common/drukcommon/events.py → Event`):

```json
{
  "id": "6f1c…",                 // unique per event; consumers use it to ignore duplicates
  "type": "incident.created",    // = routing key
  "source": "incident",          // publishing service
  "occurred_at": "2026-10-21T05:17:06.016+00:00",
  "data": { … }                  // the payload below
}
```

The W3C `traceparent` header travels in the AMQP message headers, so one trace spans publisher and consumer.

## Queues and bindings

| Queue | Consumer | Bound to |
|---|---|---|
| `dispatch.requests` (work queue; HPA scales on its depth) | dispatch | n/a (published to directly) |
| `dispatch.releases` | dispatch | `incident.status_changed`, `dispatch.release_requested` |
| `incident.dispatch-results` | incident | `dispatch.assigned`, `dispatch.unassigned` |
| `notification.events` | notification | `incident.created`, `incident.status_changed`, `dispatch.assigned`, `alert.issued` |
| `analytics.events` | analytics (scaffold) | `incident.created`, `incident.status_changed`, `dispatch.assigned` |
| `audit.events` | audit (scaffold) | `#` (everything) |
| `drukrescue.dead-letter` | none (alert fires) | messages that failed twice |

## Events

### `incident.created` (published by incident)

The full incident as returned by `GET /incidents/{id}`:

```json
{ "id": "INC-2026-001", "type": "FLOOD", "severity": "HIGH", "status": "REPORTED",
  "description": "…", "lat": 27.4447, "lng": 89.6476, "district": "Thimphu", "location_name": "Babesa",
  "photo_url": null, "reporter_id": "<user id>",
  "assigned_responder_id": null, "assigned_responder_user_id": null, "assigned_responder_name": null,
  "assigned_team": null, "assigned_vehicle_id": null, "assigned_vehicle_name": null, "eta_minutes": null,
  "created_at": "…", "updated_at": "…", "verified_at": null, "dispatched_at": null, "resolved_at": null }
```

### `incident.status_changed` (incident)

Same snapshot as above (after the change), plus:

| Field | Meaning |
|---|---|
| `from_status` | status before the change |
| `stage` | responder progress: `ACCEPTED`, `EN_ROUTE`, `ON_SCENE`, `RESOLVED` (or null) |
| `note` | human-readable note |
| `actor_id` | user id, or `system:<service>` |

Also emitted for progress stages that don't change the status (e.g. `EN_ROUTE`), in which case `from_status == status`.

### Queue message `dispatch.requested` → `dispatch.requests` (incident; dispatch re-queues retries)

```json
{ "incident_id": "INC-2026-001", "type": "FLOOD", "severity": "HIGH", "lat": 27.44, "lng": 89.64,
  "district": "Thimphu", "location_name": "Babesa", "reporter_id": "<user id>",
  "reported_at": "…", "attempt": 1, "excluded_responder_ids": [] }
```

`excluded_responder_ids` is optional. It's for the reject flow (TASKS.md B4).

### `dispatch.assigned` (dispatch)

```json
{ "incident_id": "INC-2026-001", "incident_type": "FLOOD", "severity": "HIGH", "district": "Thimphu",
  "location_name": "Babesa", "reporter_id": "<user id>",
  "responder_id": 4, "responder_user_id": "<user id or null>", "responder_name": "…", "team": "Rescue Team 04",
  "vehicle_id": 7, "vehicle_name": "BP-1-R0001", "vehicle_kind": "RESCUE",
  "distance_km": 0.12, "eta_minutes": 0.3, "time_to_dispatch_seconds": 41.2, "assigned_at": "…" }
```

### `dispatch.unassigned` (dispatch)

No free team/vehicle after `DISPATCH_MAX_ATTEMPTS`: `{ "incident_id", "reason", "attempts" }`.
The incident stays `VERIFIED`; an admin can re-dispatch.

### `dispatch.release_requested` (incident)

Units were assigned to an incident that had been cancelled in the meantime:
`{ "incident_id", "assigned_responder_id", "assigned_vehicle_id", "reason" }`. Dispatch frees them.

### `alert.issued` (alert, to be built in TASKS.md B1)

```json
{ "alert_id": 1, "title": "Flash flood warning", "message": "Move to higher ground", "district": "Thimphu",
  "severity": "CRITICAL", "issued_by": "<admin user id>", "expires_at": "… or null" }
```

## Rules for consumers

1. **Idempotent:** the same event can arrive twice (at-least-once delivery). Dedupe on `id` or make the update naturally idempotent.
2. **Don't fail forever:** a handler that raises gets one redelivery, then the message is dead-lettered.
   For "try again later" situations, catch the error and re-queue yourself (see `retry_later` in Dispatch).
3. **Never read another service's database:** if you need data, keep your own copy from events or call its REST API.
