// FelfelDM browser extension background script.
//
// Runs as an MV3 service worker on Chrome (background.service_worker) and
// as a non-persistent MV3 background page on Firefox
// (background.scripts + type: module). Chrome has no `browser` global, so
// the shim below is mandatory and must stay the very first statement.

const browser = globalThis.browser ?? globalThis.chrome;

const SERVER_GUI = "http://localhost:8766";
const SERVER_DAEMON = "http://localhost:8765";
const ICON_URL = browser.runtime.getURL("icons/icon128.png");

// How long a URL stays in the ignore set. A context-menu action asks the
// DM to fetch a URL; if the browser also fires downloads.onCreated for the
// same URL we must not intercept it again. Entries expire so the set can't
// grow forever and a later genuine download is never skipped by a stale
// entry.
const IGNORE_TTL_MS = 15000;
const CONNECTION_CACHE_MS = 2000;

// ===== Connection state =====
// Under MV3 the background context is torn down when idle, so anything we
// want to survive a restart lives in storage; these are just a cache of it.
let isConnected = false;
let activeServer = null;
let lastConnectionCheck = 0;

// url -> expiry timestamp (ms). Memory-only on purpose: it only needs to
// survive a few seconds of in-flight interception.
const ignored = new Map();

function rememberIgnored(urls) {
  if (!urls) return;
  const now = Date.now();
  for (const url of urls) {
    if (url) ignored.set(url, now + IGNORE_TTL_MS);
  }
}

function consumeIgnored(url) {
  const expiry = ignored.get(url);
  if (expiry === undefined) return false;
  ignored.delete(url);
  return expiry > Date.now();
}

function pruneIgnored() {
  const now = Date.now();
  for (const [url, expiry] of ignored) {
    if (expiry <= now) ignored.delete(url);
  }
}

// ===== Connection helpers =====
async function isCatchEnabled() {
  try {
    const data = await browser.storage.local.get("catchDownloads");
    return data.catchDownloads !== undefined ? data.catchDownloads : true;
  } catch {
    // If storage is unavailable, fail open (keeping the previous default
    // of "catching enabled") rather than silently disabling interception.
    return true;
  }
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
  if (!force && now - lastConnectionCheck < CONNECTION_CACHE_MS) {
    return { connected: isConnected, server: activeServer };
  }
  lastConnectionCheck = now;
  pruneIgnored();

  try {
    const [guiOk, daemonOk] = await Promise.all([ping(8766), ping(8765)]);

    if (guiOk) {
      activeServer = SERVER_GUI;
      isConnected = true;
    } else if (daemonOk) {
      activeServer = SERVER_DAEMON;
      isConnected = true;
    } else {
      activeServer = null;
      isConnected = false;
    }
  } catch (e) {
    console.error("Connection check error:", e);
    isConnected = false;
    activeServer = null;
  }

  await updateBadge();
  return { connected: isConnected, server: activeServer };
}

async function updateBadge() {
  try {
    const catchEnabled = await isCatchEnabled();

    if (isConnected) {
      if (catchEnabled) {
        await browser.action.setBadgeText({ text: "⬇" });
        await browser.action.setBadgeBackgroundColor({ color: "#27ae60" });
        await browser.action.setTitle({ title: "FelfelDM ⬇ Ready" });
      } else {
        await browser.action.setBadgeText({ text: "⛔" });
        await browser.action.setBadgeBackgroundColor({ color: "#f39c12" });
        await browser.action.setTitle({ title: "FelfelDM ⛔ Catch Off" });
      }
    } else {
      await browser.action.setBadgeText({ text: "✕" });
      await browser.action.setBadgeBackgroundColor({ color: "#e74c3c" });
      await browser.action.setTitle({ title: "FelfelDM ✕ Offline" });
    }
  } catch (e) {
    console.error("Badge update error:", e);
  }
}

async function notify(message, priority) {
  // `notifications` is optional at the manifest level for safety: if it is
  // missing the call would throw a TypeError, which must never break the
  // caller's control flow.
  try {
    if (!browser.notifications?.create) return;
    await browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message,
      ...(priority ? { priority } : {}),
    });
  } catch (e) {
    console.error("Notification error:", e);
  }
}

// ===== Periodic refresh =====
// MV3 service workers are killed when idle, so a long-lived setInterval is
// not reliable. chrome.alarms is the supported way to get periodic wakeups.
const REFRESH_ALARM = "felfeldm-refresh";

function ensureRefreshAlarm() {
  try {
    if (browser.alarms?.create) {
      browser.alarms.create(REFRESH_ALARM, { periodInMinutes: 1 });
    }
  } catch (e) {
    console.error("Alarm setup error:", e);
  }
}

if (browser.alarms?.onAlarm) {
  browser.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === REFRESH_ALARM) {
      checkConnection(true);
    }
  });
}

if (browser.storage?.onChanged) {
  browser.storage.onChanged.addListener((changes) => {
    if (changes.catchDownloads) {
      updateBadge();
    }
  });
}

// ===== Send URLs to the download manager =====
// Returns true only when the DM has explicitly acknowledged the URLs.
// Callers must not treat a browser-side download as replaceable until this
// returns true.
async function send(urls) {
  if (!urls || urls.length === 0) return false;

  const { connected, server } = await checkConnection(true);
  if (!connected || !server) {
    await notify(
      "⚠️ FelfelDM is not running!\nPlease start the application first.",
      2,
    );
    return false;
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    const r = await fetch(`${server}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (r.ok) {
      notify(`✅ Added ${urls.length} download(s)`);
      return true;
    }
    console.error("FelfelDM rejected /add with HTTP", r.status);
    return false;
  } catch (e) {
    console.error("Send error:", e);
    return false;
  }
}

// ===== Download interception =====
//
// Ordering matters. The previous implementation cancelled the browser
// download FIRST and only then told the DM, so any failure in between
// (DM closed, RPC error, non-200) lost the file outright. Now we ask the
// DM first and only cancel once it has acknowledged the URL; if anything
// fails we leave the browser download untouched.
browser.downloads.onCreated.addListener(async (item) => {
  if (!item.url || !item.url.startsWith("http")) return;

  if (!(await isCatchEnabled())) return;
  if (!item.url || consumeIgnored(item.url)) return;

  const { connected } = await checkConnection(false);
  if (!connected) {
    console.log("⚠️ FelfelDM not connected, leaving download to browser");
    return;
  }

  const accepted = await send([item.url]);

  if (!accepted) {
    // The DM never took responsibility for this URL. Tell the user and
    // leave the browser download running.
    await notify(
      "⚠️ FelfelDM did not accept the download.\nThe browser will handle it instead.",
    );
    return;
  }

  try {
    await browser.downloads.cancel(item.id);
  } catch (e) {
    console.error("Cancel error (DM already has the file):", e);
  }

  setTimeout(async () => {
    try {
      await browser.downloads.erase({ id: item.id });
    } catch (e) {
      console.error("Erase error:", e);
    }
  }, 300);
});

// ===== Context Menus =====
const MENU_ITEMS = [
  { id: "download-link", title: "Download with FelfelDM", contexts: ["link"] },
  {
    id: "download-image",
    title: "Download Image with FelfelDM",
    contexts: ["image"],
  },
  {
    id: "download-video",
    title: "Download Video with FelfelDM",
    contexts: ["video"],
  },
  {
    id: "download-audio",
    title: "Download Audio with FelfelDM",
    contexts: ["audio"],
  },
  {
    id: "download-page",
    title: "Download Current Page with FelfelDM",
    contexts: ["page"],
  },
  {
    id: "download-selected-links",
    title: "Download Selected Links",
    contexts: ["selection"],
  },
];

async function createContextMenus() {
  try {
    if (browser.contextMenus.removeAll) {
      await browser.contextMenus.removeAll();
    }
    for (const item of MENU_ITEMS) {
      browser.contextMenus.create(item);
    }
  } catch (e) {
    console.error("Context menu setup error:", e);
  }
}

browser.runtime.onInstalled.addListener(() => {
  createContextMenus();
  ensureRefreshAlarm();
});

browser.runtime.onStartup?.addListener(() => {
  createContextMenus();
  ensureRefreshAlarm();
});

// Read the current selection's links from the page.
//
// Uses scripting.executeScript against the active tab, which is covered by
// the `activeTab` permission, so the extension no longer needs a
// content script injected into every site the user visits.
async function getSelectedLinks(tabId) {
  try {
    const results = await browser.scripting.executeScript({
      target: { tabId },
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
    return results?.[0]?.result || [];
  } catch (e) {
    console.error("Selected-links extraction failed:", e);
    return [];
  }
}

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!(await isCatchEnabled())) {
    await notify("⛔ Download catching is disabled. Enable it from the popup.");
    return;
  }

  const { connected } = await checkConnection(false);
  if (!connected) {
    await notify("⚠️ FelfelDM is not running!", 2);
    return;
  }

  try {
    switch (info.menuItemId) {
      case "download-link":
        rememberIgnored([info.linkUrl]);
        await send([info.linkUrl]);
        break;

      case "download-image":
      case "download-video":
      case "download-audio":
        rememberIgnored([info.srcUrl]);
        await send([info.srcUrl]);
        break;

      case "download-page":
        rememberIgnored([tab?.url]);
        await send([tab?.url]);
        break;

      case "download-selected-links": {
        const links = await getSelectedLinks(tab.id);
        if (links.length) {
          rememberIgnored(links);
          await send(links);
        } else {
          await notify("No links found in selection.");
        }
        break;
      }
    }
  } catch (e) {
    console.error("Context menu handler error:", e);
    await notify("⚠️ Could not send the download to FelfelDM.");
  }
});

// ===== Message handling =====
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "toggle_catch") {
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
    checkConnection(true).then(({ connected }) => {
      sendResponse({ status: connected ? "ok" : "error" });
    });
    return true;
  }
});

// Warm up on load.
createContextMenus();
ensureRefreshAlarm();
checkConnection(true);