# Contributing

## First time setup

```bash
git clone https://github.com/KeldenPDorji/DrukRescue.git && cd DrukRescue
make venv        # Python 3.12+ virtualenv with every service's dependencies
make test        # all unit tests (no Docker needed)
make env && make up && make seed   # the whole platform in Docker → http://localhost:8080
```

Then read, in this order: [`rescue.md`](rescue.md) (the plan), [`docs/architecture.md`](docs/architecture.md),
[`docs/events.md`](docs/events.md) and [`TASKS.md`](TASKS.md) (find your tasks).

## Workflow

1. Pick a task from `TASKS.md`. Create a branch: `feat/B1-alert-service`, `fix/dispatch-retry`, `docs/runbook`.
2. Small commits, present tense: `alert: publish alert.issued after commit`.
3. Open a PR to `main`. CI must be green and **one teammate reviews** before merging.
   The reviewer runs the code locally for anything touching the demo flow.
4. Never push directly to `main`; CI's tag-bump commits are the only exception.

## Working on one service

```bash
make test-incident                       # its tests
cd services/incident
DATABASE_URL=sqlite:///./dev.db EVENTS_BACKEND=memory SERVICE_NAME=incident \
  ../../.venv/bin/uvicorn app.main:app --reload --port 8001
# Requests need identity headers (normally added by the gateway):
curl -H 'X-User-Id: u1' -H 'X-User-Role: CITIZEN' localhost:8001/incidents
```

Or rebuild just that container in the full stack: `docker compose up -d --build incident`.

## Code rules

- **Follow the existing services.** Use `create_app`, `Database`, `create_event_bus`, `require_roles` from `drukcommon`.
  Look at `services/vehicle` for CRUD, `services/incident` for events, and `services/dispatch` for calling other services.
- **Validate input** with Pydantic models (lengths, ranges, enums). **Check roles** in the service, even if the gateway checks too.
- **Commit to the DB, then publish the event.** Consumers must be idempotent (see `docs/events.md`).
- **Tests** for every endpoint and event handler (happy path, validation, permissions). `make lint` must be clean.
- **Never read another service's tables.** Use its REST API or keep your own copy from events.
- Changing an event payload? Update `docs/events.md` in the same PR.

## Secrets

- Never commit `.env`, kubeconfigs, tokens or passwords. `.gitignore` covers the usual files; check `git diff --cached` anyway.
- Local secrets come from `make env`, cluster secrets from `scripts/create-secrets.sh`. Neither is ever committed.
- If a secret is pushed by accident, **rotate it**. Deleting the commit is not enough.
