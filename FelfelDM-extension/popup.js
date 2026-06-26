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

ping();

const checkbox = document.getElementById("catchDownloads");

browser.storage.local.get("catchDownloads").then((data) => {
  checkbox.checked = data.catchDownloads ?? true;
});

checkbox.addEventListener("change", () => {
  browser.storage.local.set({
    catchDownloads: checkbox.checked,
  });
});
