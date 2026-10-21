// k6 burst test: 100 incident reports in under a minute, so the dispatch.requests queue grows
// and the Dispatch HPA scales 2 -> 6 (rescue.md section 12). Owner: TASKS.md C1.
//
//   k6 run -e BASE_URL=http://drukrescue.local -e CITIZEN_EMAIL=... -e CITIZEN_PASSWORD=... \
//          -e ADMIN_EMAIL=... -e ADMIN_PASSWORD=... loadtest/burst.js
//
// TODO(C1):
//   - decide: AUTO_VERIFY=true in deploy/envs/demo (Git commit), or verify each report as admin here (sketched below)
//   - make sure there are enough responders/vehicles seeded (or that units get released), otherwise most
//     requests end up "unassigned" after 3 attempts. That's fine for the scaling demo but explain it.
//   - export a summary (handleSummary) into loadtest/results/ for the test report
import http from "k6/http";
import { check } from "k6";

const BASE = `${__ENV.BASE_URL || "http://localhost:8000"}/api`;
const TYPES = ["FLOOD", "LANDSLIDE", "FIRE", "MEDICAL", "ACCIDENT"];

export const options = {
  scenarios: {
    burst: { executor: "shared-iterations", vus: 20, iterations: 100, maxDuration: "60s" },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:report}": ["p(95)<1000"],
  },
};

function login(email, password) {
  const res = http.post(`${BASE}/auth/login`, JSON.stringify({ email, password }), {
    headers: { "Content-Type": "application/json" },
  });
  check(res, { "logged in": (r) => r.status === 200 });
  return res.json("access_token");
}

export function setup() {
  return {
    citizen: login(__ENV.CITIZEN_EMAIL, __ENV.CITIZEN_PASSWORD),
    admin: __ENV.ADMIN_EMAIL ? login(__ENV.ADMIN_EMAIL, __ENV.ADMIN_PASSWORD) : null,
  };
}

export default function (tokens) {
  const body = {
    type: TYPES[Math.floor(Math.random() * TYPES.length)],
    severity: "HIGH",
    description: "Load test report",
    lat: 27.44 + Math.random() * 0.06,
    lng: 89.62 + Math.random() * 0.05,
    district: "Thimphu",
    location_name: "Load test",
  };
  const res = http.post(`${BASE}/incidents`, JSON.stringify(body), {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens.citizen}` },
    tags: { name: "report" },
  });
  check(res, { "reported (201)": (r) => r.status === 201 });

  if (tokens.admin && res.status === 201) {
    const verify = http.post(`${BASE}/incidents/${res.json("id")}/verify`, null, {
      headers: { Authorization: `Bearer ${tokens.admin}` },
      tags: { name: "verify" },
    });
    check(verify, { "verified (200)": (r) => r.status === 200 });
  }
}
