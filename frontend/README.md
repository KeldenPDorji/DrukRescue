# Frontend (task **B3**)

One web app with three role-based views. It is plain HTML + ES modules served by nginx, with no build step.
If the team prefers React/Vite, swap it in, but keep the same contract: the app is served on port 8080,
`/healthz` returns 200, and API calls go to `/api/...`.

"Live" status is **polling every 5 s** (`poll()` in `js/api.js`). There are no WebSockets, by design.

## What's done

- Login and citizen registration, with the JWT kept in `sessionStorage`
- Notifications panel (polls `/api/notifications/me`)
- **Citizen view**: report an emergency (uses browser geolocation, falls back to Babesa) and a tracker for "my reports"

## What's left (B3)

| View | Spec |
|---|---|
| Responder | `js/views/responder.js`: status toggle, share location, assignments with En route / On scene / Resolved buttons |
| Admin | `js/views/admin.js`: incidents table with Verify / Cancel / Re-dispatch, timeline, units, alert form, stats |
| Citizen | add "Nearest shelters" (B2) and "Active alerts" (B1) cards |

Rules:
- Build HTML from data only via `esc()` or `textContent` (XSS). The nginx CSP blocks inline scripts.
- Never put tokens in URLs or `localStorage`.

## Run it

- With everything: `make up`, then open http://localhost:8080
- Frontend only, against a running gateway: `docker compose up -d --build frontend`
