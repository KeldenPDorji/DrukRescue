// Responder view: TODO(B3). See frontend/README.md for the spec.
//
// Needed for the demo (step 5):
//   - My status: GET /responders/me; toggle AVAILABLE/OFFLINE with PATCH /responders/me/status
//   - Share location: PATCH /responders/me/location {lat, lng} (navigator.geolocation)
//   - My assignments: GET /incidents?active=true (the gateway/incident service already filters to "assigned to me")
//   - Buttons per assignment: POST /incidents/{id}/progress {stage: "EN_ROUTE" | "ON_SCENE" | "RESOLVED"}
//   - Poll every 5 s with poll() from ../api.js; escape all text with esc()
import { esc } from "../api.js";

export function renderResponder(root, user) {
  root.innerHTML = `
    <section class="card">
      <h1>Responder</h1>
      <p class="muted">Hello ${esc(user.name)}. This view is not built yet (TASKS.md B3).</p>
    </section>`;
}
