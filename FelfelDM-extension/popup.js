const SERVER = "http://localhost:8765";

async function ping() {
  const statusEl = document.getElementById("status");

  try {
    const r = await fetch(`${SERVER}/ping`);

    if (r.ok) {
      statusEl.textContent = "🟢 Connected to FelfelDM";
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

ping();

setInterval(ping, 10000);
