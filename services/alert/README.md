# Alert service (scaffold, task **B1**)

The command centre issues area-wide warnings, e.g. *"Flash flood warning – Babesa"* (demo step 4).

## Data model (suggested)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| title | str(200) | |
| message | str(1000) | |
| district | str(64), nullable | null = nationwide |
| severity | enum | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| issued_by | str(64) | admin user id, from `X-User-Id` |
| issued_at | timestamptz | |
| expires_at | timestamptz, nullable | |
| cancelled_at | timestamptz, nullable | |

## Endpoints (gateway: `/api/alerts/...`; writes are ADMIN-only)

| Method | Path | Who | Behaviour |
|---|---|---|---|
| GET | `/alerts?district=&active=true` | any user | newest first; `active` = not expired, not cancelled |
| GET | `/alerts/{id}` | any user | |
| POST | `/alerts` | ADMIN | save, then publish `alert.issued`; 201 |
| POST | `/alerts/{id}/cancel` | ADMIN | sets `cancelled_at`; optionally publish `alert.cancelled` |

### Event you must publish

```python
bus.publish("alert.issued", {
    "alert_id": alert.id, "title": ..., "message": ..., "district": ..., "severity": ...,
    "issued_by": principal.user_id, "expires_at": iso(alert.expires_at),
})
```

Notification (`services/notification/app/messages.py`) turns this into a notification for everyone,
and Audit will log it. See `docs/events.md`.

## Done when

- [ ] Endpoints and tests (use `bus.sent("alert.issued")` to assert the event was published, as the Incident tests do)
- [ ] End to end: an admin POSTs an alert, and a citizen sees it in `GET /api/notifications/me`
- [ ] The admin page in the frontend has an "Issue alert" form (coordinate with B3)
