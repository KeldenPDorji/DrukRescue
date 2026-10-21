## What

<!-- One or two sentences. Link the task, e.g. "Implements TASKS.md B1 (Alert service)". -->

## How I tested it

- [ ] `make test-<service>` passes (new endpoints/handlers have tests)
- [ ] `make lint` is clean
- [ ] If I changed charts: `make helm-template` renders
- [ ] If I changed an event payload: `docs/events.md` is updated and consumers still work

## Checklist

- [ ] No secrets, passwords or tokens in the diff (`.env` and kubeconfigs stay local)
- [ ] User input is validated (Pydantic) and role checks are in place (`require_roles`)
