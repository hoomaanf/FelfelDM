// Chrome has no `browser` global; Firefox provides both. This shim must be
// the first statement, before any browser.* reference.
const browser = globalThis.browser ?? globalThis.chrome;

const SERVER_GUI = "http://localhost:8766";
const SERVER_DAEMON = "http://localhost:8765";

const statusEl = document.getElementById("status");
const checkbox = document.getElementById("catchDownloads");
const statusText = document.getElementById("catchStatus");
const toggleContainer = document.getElementById("toggleContainer");

async function pingPort(url) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1000);
    const r = await fetch(`${url}/ping`, { signal: controller.signal });
    clearTimeout(timeoutId);
    return r.ok;
  } catch {
    return false;
  }
}

async function ping() {
  const guiOk = await pingPort(SERVER_GUI);
  const daemonOk = guiOk ? false : await pingPort(SERVER_DAEMON);

  if (guiOk) {
    statusEl.textContent = "🟢 Connected to FelfelDM (GUI)";
    statusEl.className = "connected";
    return true;
  }
  if (daemonOk) {
    statusEl.textContent = "🟢 Connected to FelfelDM (Service)";
    statusEl.className = "connected";
    return true;
  }
  statusEl.textContent = "🔴 FelfelDM is not running";
  statusEl.className = "disconnected";
  return false;
}

function updateStatusText(enabled) {
  if (enabled) {
    statusText.textContent = "✅ Active - Downloads will be intercepted";
    statusText.className = "status-text active";
  } else {
    statusText.textContent = "⛔ Inactive - Downloads will NOT be intercepted";
    statusText.className = "status-text inactive";
  }
}

function toggleCatch() {
  const isEnabled = !checkbox.checked;
  checkbox.checked = isEnabled;

  browser.storage.local
    .set({ catchDownloads: isEnabled })
    .catch((err) => console.error("Could not save setting:", err));
  updateStatusText(isEnabled);

  browser.runtime
    .sendMessage({ action: "toggle_catch", enabled: isEnabled })
    .catch((err) => console.log("Message error:", err));
}

async function init() {
  try {
    const data = await browser.storage.local.get("catchDownloads");
    const isEnabled =
      data.catchDownloads !== undefined ? data.catchDownloads : true;
    checkbox.checked = isEnabled;
    updateStatusText(isEnabled);
  } catch (e) {
    console.error("Could not load setting:", e);
  }

  checkbox.addEventListener("change", toggleCatch);
  toggleContainer.addEventListener("click", (e) => {
    if (e.target.tagName !== "INPUT") {
      toggleCatch();
    }
  });
  

  await ping();
  setInterval(ping, 5000);
}

init();