// Citizen view: report an emergency and track your reports (polls every 5 s).
import { api, esc, poll } from "../api.js";

const TYPES = ["FLOOD", "GLOF", "LANDSLIDE", "EARTHQUAKE", "FIRE", "ACCIDENT", "MEDICAL", "OTHER"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const BABESA = { lat: 27.4447, lng: 89.6476 }; // fallback when the browser can't give a location

function steps(inc) {
  const order = ["REPORTED", "VERIFIED", "DISPATCHED", "IN_PROGRESS", "RESOLVED"];
  if (inc.status === "CANCELLED") return `<span>✕ Cancelled</span>`;
  const reached = order.indexOf(inc.status);
  const labels = ["Reported", "Verified", "Team assigned", "On scene", "Resolved"];
  return labels.map((l, i) => `<span class="${i <= reached ? "done" : ""}">${i <= reached ? "✓" : "○"} ${l}</span>`).join("");
}

export function renderCitizen(root) {
  root.innerHTML = `
    <section class="card">
      <h1>Report an emergency</h1>
      <form id="report">
        <div class="row">
          <label>Type <select name="type">${TYPES.map((t) => `<option>${t}</option>`).join("")}</select></label>
          <label>Severity <select name="severity">${SEVERITIES.map((s) => `<option ${s === "MEDIUM" ? "selected" : ""}>${s}</option>`).join("")}</select></label>
        </div>
        <label>What is happening? <textarea name="description" required minlength="3" maxlength="2000"></textarea></label>
        <div class="row">
          <label>Place <input name="location_name" placeholder="e.g. Babesa"></label>
          <label>District <input name="district" placeholder="e.g. Thimphu"></label>
        </div>
        <button>Send report</button>
        <p class="error" id="report-error"></p>
      </form>
    </section>
    <section class="card">
      <h1>My reports</h1>
      <div id="my-incidents" class="muted">Loading…</div>
    </section>
    <!-- TODO(B2/B3): "Nearest shelters" card using GET /shelters/nearby?lat=&lng= -->
    <!-- TODO(B1/B3): "Active alerts" card using GET /alerts?active=true -->`;

  document.getElementById("report").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = Object.fromEntries(new FormData(e.target));
    const position = await currentPosition();
    try {
      await api("/incidents", { method: "POST", body: { ...form, ...position } });
      e.target.reset();
      refresh();
    } catch (err) {
      document.getElementById("report-error").textContent = err.message;
    }
  });

  const list = document.getElementById("my-incidents");
  const refresh = async () => {
    const incidents = await api("/incidents?limit=20").catch(() => null);
    if (!incidents) return;
    list.classList.toggle("muted", incidents.length === 0);
    list.innerHTML = incidents.length ? incidents.map((i) => `
      <div class="incident">
        <strong>${esc(i.id)}</strong> · ${esc(i.type)} · ${esc(i.location_name || i.district || "")}
        <div class="steps">${steps(i)}</div>
        ${i.assigned_team ? `<div>${esc(i.assigned_team)} with ${esc(i.assigned_vehicle_name)}${i.eta_minutes ? ` · ETA ~${Math.round(i.eta_minutes)} min` : ""}</div>` : ""}
      </div>`).join("") : "No reports yet.";
  };
  poll(refresh);
}

function currentPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(BABESA);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(BABESA),
      { timeout: 5000 },
    );
  });
}
