const SERVER_GUI = "http://localhost:8766";
const SERVER_DAEMON = "http://localhost:8765";
const ICON_URL = browser.runtime.getURL("icons/icon128.png");

// ===== Connection state =====
let isConnected = false;
let activeServer = null;
let lastConnectionCheck = 0;

// ===== Update badge =====
async function updateBadge() {
  const catchEnabled = await isCatchEnabled();

  if (isConnected) {
    if (catchEnabled) {
      browser.action.setBadgeText({ text: "⬇" });
      browser.action.setBadgeBackgroundColor({ color: "#27ae60" });
      browser.action.setTitle({ title: "FelfelDM ⬇ Ready" });
    } else {
      browser.action.setBadgeText({ text: "⛔" });
      browser.action.setBadgeBackgroundColor({ color: "#f39c12" });
      browser.action.setTitle({ title: "FelfelDM ⛔ Catch Off" });
    }
  } else {
    browser.action.setBadgeText({ text: "✕" });
    browser.action.setBadgeBackgroundColor({ color: "#e74c3c" });
    browser.action.setTitle({ title: "FelfelDM ✕ Offline" });
  }
}

async function isCatchEnabled() {
  const data = await browser.storage.local.get("catchDownloads");
  return data.catchDownloads !== undefined ? data.catchDownloads : true;
}

async function ping(port) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1000);
    const r = await fetch(`http://localhost:${port}/ping`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return r.ok;
  } catch {
    return false;
  }
}

async function checkConnection(force = false) {
  const now = Date.now();
  if (!force && now - lastConnectionCheck < 2000) {
    return isConnected;
  }
  lastConnectionCheck = now;

  try {
    const [guiOk, daemonOk] = await Promise.all([ping(8766), ping(8765)]);

    if (guiOk) {
      activeServer = SERVER_GUI;
      isConnected = true;
      console.log("✅ Connected to GUI on port 8766");
    } else if (daemonOk) {
      activeServer = SERVER_DAEMON;
      isConnected = true;
      console.log("✅ Connected to Daemon on port 8765");
    } else {
      activeServer = null;
      isConnected = false;
      console.log("⚠️ No FelfelDM server found");
    }

    await updateBadge();
  } catch (e) {
    console.error("Connection check error:", e);
    isConnected = false;
    activeServer = null;
    await updateBadge();
  }

  return isConnected;
}

// ===== Storage change listener for badge update =====
browser.storage.onChanged.addListener((changes, namespace) => {
  if (changes.catchDownloads) {
    updateBadge();
  }
});

// ===== Check connection every 3 seconds =====
setInterval(() => checkConnection(true), 3000);
setTimeout(() => checkConnection(true), 500);

// ===== Send URLs =====
async function send(urls) {
  if (!urls || urls.length === 0) return false;
  const connected = await checkConnection(true);
  if (!connected) {
    await browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message:
        "⚠️ FelfelDM is not running!\nPlease start the application first.",
      priority: 2,
    });
    return false;
  }

  const server = activeServer;
  if (!server) {
    await browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message: "⚠️ Could not connect to FelfelDM.",
    });
    return false;
  }

  try {
    const r = await fetch(`${server}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    });

    if (r.ok) {
      browser.notifications.create({
        type: "basic",
        iconUrl: ICON_URL,
        title: "🌶️ FelfelDM",
        message: `✅ Added ${urls.length} download(s)`,
      });
      return true;
    }
    return false;
  } catch (e) {
    console.error("Send error:", e);
    return false;
  }
}

// ===== Download interception =====
const ignored = new Set();

browser.downloads.onCreated.addListener(async (item) => {
  if (!item.url || !item.url.startsWith("http")) return;

  const enabled = await isCatchEnabled();
  if (!enabled) {
    console.log("⛔ Download catching is disabled");
    return;
  }

  if (ignored.has(item.url)) {
    ignored.delete(item.url);
    return;
  }

  const connected = await checkConnection(false);
  if (!connected) {
    console.log("⚠️ FelfelDM not connected, not intercepting");
    return;
  }

  try {
    await browser.downloads.cancel(item.id);
    console.log(`⏸️ Cancelled download: ${item.url}`);
  } catch (e) {
    console.error("Cancel error:", e);
    return;
  }

  const sent = await send([item.url]);

  if (sent) {
    setTimeout(async () => {
      try {
        await browser.downloads.erase({ id: item.id });
        console.log(`🗑️ Removed from history: ${item.url}`);
      } catch (e) {
        console.error("Erase error:", e);
      }
    }, 300);
  }
});

// ===== Context Menus =====
browser.runtime.onInstalled.addListener(() => {
  if (browser.contextMenus.removeAll) {
    browser.contextMenus.removeAll();
  }

  browser.contextMenus.create({
    id: "download-link",
    title: "Download with FelfelDM",
    contexts: ["link"],
  });

  browser.contextMenus.create({
    id: "download-image",
    title: "Download Image with FelfelDM",
    contexts: ["image"],
  });

  browser.contextMenus.create({
    id: "download-video",
    title: "Download Video with FelfelDM",
    contexts: ["video"],
  });

  browser.contextMenus.create({
    id: "download-audio",
    title: "Download Audio with FelfelDM",
    contexts: ["audio"],
  });

  browser.contextMenus.create({
    id: "download-page",
    title: "Download Current Page with FelfelDM",
    contexts: ["page"],
  });

  browser.contextMenus.create({
    id: "download-selected-links",
    title: "Download Selected Links",
    contexts: ["selection"],
  });
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  const enabled = await isCatchEnabled();
  if (!enabled) {
    browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message: "⛔ Download catching is disabled. Enable it from the popup.",
    });
    return;
  }

  const connected = await checkConnection(false);
  if (!connected) {
    browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message: "⚠️ FelfelDM is not running!",
      priority: 2,
    });
    return;
  }

  try {
    switch (info.menuItemId) {
      case "download-link":
        ignored.add(info.linkUrl);
        await send([info.linkUrl]);
        break;

      case "download-image":
      case "download-video":
      case "download-audio":
        ignored.add(info.srcUrl);
        await send([info.srcUrl]);
        break;

      case "download-page":
        ignored.add(tab.url);
        await send([tab.url]);
        break;

      case "download-selected-links": {
        try {
          let links = [];
          if (typeof browser.tabs.sendMessage === "function") {
            links = await browser.tabs.sendMessage(tab.id, {
              type: "getSelectedLinks",
            });
          } else {
            const results = await browser.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const selection = window.getSelection();
                if (!selection || selection.rangeCount === 0) return [];
                const fragment = selection.getRangeAt(0).cloneContents();
                return [
                  ...new Set(
                    [...fragment.querySelectorAll("a[href]")]
                      .map((a) => a.href)
                      .filter(Boolean),
                  ),
                ];
              },
            });
            links = results[0]?.result || [];
          }

          if (links && links.length) {
            await send(links);
          } else {
            browser.notifications.create({
              type: "basic",
              iconUrl: ICON_URL,
              title: "🌶️ FelfelDM",
              message: "No links found in selection.",
            });
          }
        } catch (e) {
          console.error(e);
          browser.notifications.create({
            type: "basic",
            iconUrl: ICON_URL,
            title: "🌶️ FelfelDM",
            message: "Error getting selected links.",
          });
        }
        break;
      }
    }
  } catch (e) {
    console.error(e);
  }
});

// ===== Message handling =====
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("📨 Message received:", message);

  if (message.action === "toggle_catch") {
    console.log(
      `🔄 Download catching: ${message.enabled ? "ON 🟢" : "OFF 🔴"}`,
    );
    updateBadge();
    return;
  }

  if (message.action === "add_urls") {
    send(message.urls).then((result) => {
      sendResponse({ status: result ? "success" : "error" });
    });
    return true;
  }

  if (message.action === "ping") {
    ping(8766).then((result) => {
      sendResponse({ status: result ? "ok" : "error" });
    });
    return true;
  }
});

console.log("🌶️ FelfelDM Extension loaded!");
console.log("   GUI: http://localhost:8766");
console.log("   Daemon: http://localhost:8765");
