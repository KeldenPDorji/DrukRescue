// Command Centre (admin) view: TODO(B3). See frontend/README.md for the spec.
//
// Needed for the demo (steps 2 and 4):
//   - Incidents table: GET /incidents?active=true (poll every 5 s)
//       buttons: Verify  -> POST /incidents/{id}/verify
//                Cancel  -> POST /incidents/{id}/cancel {reason}
//                Re-dispatch (when VERIFIED and stuck) -> POST /incidents/{id}/redispatch
//   - Timeline drawer: GET /incidents/{id}/timeline
//   - Units: GET /responders, GET /vehicles (status + position)
//   - Issue alert form: POST /alerts {title, message, district, severity}       (needs B1)
//   - Stats: GET /analytics/stats                                                (needs D3)
//   - Create responder accounts: POST /auth/accounts {..., role: "RESPONDER"} then POST /responders {user_id, ...}
import { esc } from "../api.js";

export function renderAdmin(root, user) {
  root.innerHTML = `
    <section class="card">
      <h1>Command Centre</h1>
      <p class="muted">Hello ${esc(user.name)}. This view is not built yet (TASKS.md B3).</p>
    </section>`;
}
