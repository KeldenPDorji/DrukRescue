# Audit service (scaffold, task **A1**)

An append-only record of everything important that happened, built from events.

## Data model (suggested)

`audit_log`

| Column | Notes |
|---|---|
| id | int PK |
| event_id | unique (the event's `id`, which makes redelivery harmless) |
| event_type | e.g. `incident.status_changed` |
| source | publishing service |
| actor_id | `data.actor_id`, else `data.reporter_id` / `data.issued_by`, else null |
| entity_id | `data.incident_id` or `data.id` or `data.alert_id` |
| occurred_at | event timestamp |
| payload | the full `data` as JSON text |

**Append-only.** There are no update or delete endpoints. For a strong viva point, add a hash chain:
each row stores `sha256(prev_hash + event_id + payload)`, and `GET /audit/verify` recomputes it to show nothing was altered.

## Endpoint (gateway: `/api/audit`, ADMIN only)

`GET /audit?event_type=&entity_id=&actor_id=&since=&limit=100` returns entries, newest first.

## Done when

- [ ] Every event type in `docs/events.md` lands in the log (the consumer is bound to `#`)
- [ ] Duplicates ignored, with tests
- [ ] Query endpoint with filters, with tests
- [ ] Optional: hash chain + `/audit/verify`
