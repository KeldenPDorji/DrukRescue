import { api, clearSession, esc, poll, saveSession, session } from "./api.js";
import { renderAdmin } from "./views/admin.js";
import { renderCitizen } from "./views/citizen.js";
import { renderResponder } from "./views/responder.js";

const app = document.getElementById("app");
const VIEWS = { CITIZEN: renderCitizen, RESPONDER: renderResponder, ADMIN: renderAdmin };

function renderLogin() {
  app.innerHTML = `
    <section class="card">
      <h1>Log in</h1>
      <form id="login">
        <label>Email <input name="email" type="email" required autocomplete="username"></label>
        <label>Password <input name="password" type="password" required autocomplete="current-password"></label>
        <button>Log in</button>
        <p class="error" id="login-error"></p>
      </form>
    </section>
    <section class="card">
      <h1>New here? Register as a citizen</h1>
      <form id="register">
        <label>Name <input name="name" required></label>
        <label>Email <input name="email" type="email" required></label>
        <label>Phone <input name="phone" type="tel"></label>
        <label>Password (min 8) <input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
        <button>Register</button>
        <p class="error" id="register-error"></p>
      </form>
    </section>`;

  for (const [id, path] of [["login", "/auth/login"], ["register", "/auth/register"]]) {
    document.getElementById(id).addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target));
      try {
        saveSession(await api(path, { method: "POST", body }));
        start();
      } catch (err) {
        document.getElementById(`${id}-error`).textContent = err.message;
      }
    });
  }
}

function startNotifications() {
  const panel = document.getElementById("notifications");
  const list = document.getElementById("notification-list");
  panel.hidden = false;
  poll(async () => {
    const items = await api("/notifications/me?limit=10").catch(() => []);
    list.innerHTML = items.length
      ? items.map((n) => `<li><strong>${esc(n.title)}</strong><br>${esc(n.message)}</li>`).join("")
      : `<li class="muted">Nothing yet.</li>`;
  });
}

function start() {
  const s = session();
  const logout = document.getElementById("logout");
  if (!s) {
    logout.hidden = true;
    document.getElementById("whoami").textContent = "";
    return renderLogin();
  }
  document.getElementById("whoami").textContent = `${s.user.name} · ${s.user.role}`;
  logout.hidden = false;
  logout.onclick = () => { clearSession(); location.reload(); };
  startNotifications();
  VIEWS[s.user.role](app, s.user);
}

start();
