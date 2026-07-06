const SERVER_GUI = "http://localhost:8766";
const SERVER_DAEMON = "http://localhost:8765";

async function ping() {
  const statusEl = document.getElementById("status");

  try {
    // ⭐ اول GUI رو چک کن
    let guiOk = false;
    try {
      const r = await fetch(`${SERVER_GUI}/ping`, {
        signal: AbortSignal.timeout(1000),
      });
      guiOk = r.ok;
    } catch {
      guiOk = false;
    }

    // ⭐ بعد Daemon رو چک کن
    let daemonOk = false;
    if (!guiOk) {
      try {
        const r = await fetch(`${SERVER_DAEMON}/ping`, {
          signal: AbortSignal.timeout(1000),
        });
        daemonOk = r.ok;
      } catch {
        daemonOk = false;
      }
    }

    if (guiOk) {
      statusEl.textContent = "🟢 Connected to FelfelDM (GUI)";
      statusEl.className = "connected";
      return true;
    } else if (daemonOk) {
      statusEl.textContent = "🟢 Connected to FelfelDM (Service)";
      statusEl.className = "connected";
      return true;
    } else {
      statusEl.textContent = "🔴 FelfelDM is not running";
      statusEl.className = "disconnected";
      return false;
    }
  } catch {
    statusEl.textContent = "🔴 FelfelDM is not running";
    statusEl.className = "disconnected";
    return false;
  }
}

const checkbox = document.getElementById("catchDownloads");
const statusText = document.getElementById("catchStatus");
const toggleContainer = document.getElementById("toggleContainer");

browser.storage.local.get("catchDownloads").then((data) => {
  const isEnabled =
    data.catchDownloads !== undefined ? data.catchDownloads : true;
  checkbox.checked = isEnabled;
  updateStatusText(isEnabled);
  console.log("Loaded catchDownloads:", isEnabled);
});

function toggleCatch() {
  const isEnabled = !checkbox.checked;
  checkbox.checked = isEnabled;
  console.log("Toggle changed to:", isEnabled);

  browser.storage.local.set({ catchDownloads: isEnabled });
  updateStatusText(isEnabled);

  browser.runtime
    .sendMessage({
      action: "toggle_catch",
      enabled: isEnabled,
    })
    .catch((err) => console.log("Message error:", err));
}

checkbox.addEventListener("change", toggleCatch);

toggleContainer.addEventListener("click", (e) => {
  if (e.target.tagName !== "INPUT") {
    toggleCatch();
  }
});

function updateStatusText(enabled) {
  if (enabled) {
    statusText.textContent = "✅ Active - Downloads will be intercepted";
    statusText.className = "status-text active";
  } else {
    statusText.textContent = "⛔ Inactive - Downloads will NOT be intercepted";
    statusText.className = "status-text inactive";
  }
}

// ⭐ چک کردن اتصال هر 5 ثانیه
ping();
setInterval(ping, 5000);
