// FelfelDM browser extension background script.
const browser = globalThis.browser ?? globalThis.chrome;

const SERVER_GUI = "http://localhost:8766";
const SERVER_DAEMON = "http://localhost:8765";
const ICON_URL = browser.runtime.getURL("icons/icon128.png");

const IGNORE_TTL_MS = 15000;
const CONNECTION_CACHE_MS = 2000;

let isConnected = false;
let activeServer = null;
let lastConnectionCheck = 0;
const ignored = new Map();

// ── Media capture ─────────────────────────────────────────────────────
//
// Used for players that don't expose a real URL on the element (blob:/MSE).
// Responses are classified by Content-Type first and by extension second.
// HLS/DASH segments are never captured: they are useless on their own and
// used to be returned as "the" link. Manifests are kept separately because
// aria2 cannot download them (the app falls back to yt-dlp for those).
const MEDIA_EXT_RE =
  /\.(mp4|webm|m4v|mkv|mov|mp3|m4a|aac|ogg|oga|opus|flac|wav)(?:[?#]|$)/i;
const AUDIO_EXT_RE = /\.(mp3|m4a|aac|ogg|oga|opus|flac|wav)(?:[?#]|$)/i;
const MANIFEST_EXT_RE = /\.(m3u8|mpd)(?:[?#]|$)/i;
const SEGMENT_EXT_RE = /\.(ts|m4s|m4f|cmfv|cmfa)(?:[?#]|$)/i;
// YouTube is handled by yt-dlp from the page URL, never from raw streams.
const SKIP_HOSTS_RE = /(^|\.)(googlevideo\.com|youtube\.com|ytimg\.com)$/i;
const MIN_MEDIA_BYTES = 64 * 1024; // drops beacons, init segments, sprites
const MAX_CAPTURED_PER_TAB = 12;

function headerValue(headers, name) {
  const h = (headers || []).find((x) => x.name.toLowerCase() === name);
  return h && h.value ? h.value : "";
}

// Returns { kind: "file"|"manifest", mediaType: "video"|"audio", size, type }
// or null when the response is not something worth offering.
function classifyResponse(details) {
  if (details.tabId < 0) return null;
  if (details.statusCode !== 200 && details.statusCode !== 206) return null;
  if (!/^https?:/i.test(details.url)) return null;

  let host;
  try {
    host = new URL(details.url).hostname;
  } catch {
    return null;
  }
  if (SKIP_HOSTS_RE.test(host)) return null;

  const url = details.url;
  const ct = headerValue(details.responseHeaders, "content-type")
    .split(";")[0]
    .trim()
    .toLowerCase();

  if (/mpegurl|dash\+xml/.test(ct) || MANIFEST_EXT_RE.test(url)) {
    return { kind: "manifest", mediaType: "video", size: 0, type: ct };
  }

  if (
    SEGMENT_EXT_RE.test(url) ||
    ct === "video/mp2t" ||
    ct === "audio/mp2t" ||
    ct === "video/iso.segment"
  ) {
    return null;
  }

  // Total size: Content-Range's total for 206, Content-Length for 200.
  // (A 206's Content-Length is only the chunk size.)
  let size = 0;
  const range = headerValue(details.responseHeaders, "content-range");
  const m = range.match(/\/(\d+)\s*$/);
  if (m) {
    size = parseInt(m[1], 10);
  } else if (details.statusCode === 200) {
    const len = parseInt(
      headerValue(details.responseHeaders, "content-length"),
      10,
    );
    if (Number.isFinite(len)) size = len;
  }

  const ctVideo = ct.startsWith("video/");
  const ctAudio = ct.startsWith("audio/");
  const genericBinary =
    ct === "" ||
    ct === "application/octet-stream" ||
    ct === "binary/octet-stream";
  if (!ctVideo && !ctAudio && !(genericBinary && MEDIA_EXT_RE.test(url))) {
    return null;
  }

  if (size && size < MIN_MEDIA_BYTES) return null;

  const mediaType =
    ctAudio || (!ctVideo && AUDIO_EXT_RE.test(url)) ? "audio" : "video";
  return { kind: "file", mediaType, size, type: ct };
}

// Direct files win over manifests; among files the biggest one is almost
// always the real content (ads/previews are small), latest wins ties.
function pickBest(items, mediaType) {
  const want = mediaType === "audio" ? "audio" : "video";
  const files = items.filter((i) => i.kind === "file" && i.mediaType === want);
  if (files.length) {
    files.sort((a, b) => (b.size || 0) - (a.size || 0) || b.time - a.time);
    return { url: files[0].url, kind: "file", size: files[0].size || 0 };
  }
  const manifests = items
    .filter((i) => i.kind === "manifest")
    .sort((a, b) => b.time - a.time);
  if (manifests.length) {
    return { url: manifests[0].url, kind: "manifest", size: 0 };
  }
  return { url: null };
}

// Per-tab state lives in storage.session (survives the background being
// suspended, cleared when the browser closes). Read-modify-write is
// serialised so concurrent responses can't overwrite each other.
let stateChain = Promise.resolve();
function serialize(fn) {
  const run = stateChain.then(fn);
  stateChain = run.catch(() => {});
  return run;
}

const tabKey = (tabId) => `media_${tabId}`;

async function readTab(tabId) {
  const key = tabKey(tabId);
  const data = await browser.storage.session.get(key);
  return data[key] || { page: null, items: [] };
}

async function writeTab(tabId, state) {
  await browser.storage.session.set({ [tabKey(tabId)]: state });
}

browser.webRequest.onHeadersReceived.addListener(
  (details) => {
    const info = classifyResponse(details);
    if (!info) return;

    serialize(async () => {
      const state = await readTab(details.tabId);
      const existing = state.items.find((i) => i.url === details.url);
      if (existing) {
        if (info.size > (existing.size || 0)) existing.size = info.size;
        existing.time = Date.now();
      } else {
        state.items.push({ url: details.url, ...info, time: Date.now() });
        if (state.items.length > MAX_CAPTURED_PER_TAB) state.items.shift();
        console.log(
          `🎯 Captured ${info.kind}:`,
          details.url.substring(0, 120),
          info.size || "",
        );
      }
      await writeTab(details.tabId, state);
    }).catch((e) => console.error("Media capture error:", e));
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"],
);

// A new page in the tab (including SPA navigations) invalidates what we
// captured for the previous one; otherwise "Download" offered the last
// page's video. The hash is ignored so #t=30 doesn't wipe a playing video.
browser.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (!changeInfo.url) return;
  let page;
  try {
    const u = new URL(changeInfo.url);
    page = u.origin + u.pathname + u.search;
  } catch {
    return;
  }
  serialize(async () => {
    const state = await readTab(tabId);
    if (state.page !== page) await writeTab(tabId, { page, items: [] });
  }).catch((e) => console.error("Media reset error:", e));
});

browser.tabs.onRemoved.addListener((tabId) => {
  serialize(() => browser.storage.session.remove(tabKey(tabId))).catch(
    () => {},
  );
});

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

async function isCatchEnabled() {
  try {
    const data = await browser.storage.local.get("catchDownloads");
    return data.catchDownloads !== undefined ? data.catchDownloads : true;
  } catch {
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
  try {
    if (!browser.notifications?.create) return;
    await browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "FelfelDM",
      message,
      ...(priority ? { priority } : {}),
    });
  } catch (e) {
    console.error("Notification error:", e);
  }
}

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
    if (alarm.name === REFRESH_ALARM) checkConnection(true);
  });
}

if (browser.storage?.onChanged) {
  browser.storage.onChanged.addListener((changes) => {
    if (changes.catchDownloads) updateBadge();
  });
}

// ── Send URLs to /add (aria2 dialog) ──
async function send(urls) {
  if (!urls || urls.length === 0) return false;
  const { connected, server } = await checkConnection(true);
  if (!connected || !server) {
    await notify("FelfelDM is not running!", 2);
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
      return true;
    }
    return false;
  } catch (e) {
    console.error("Send error:", e);
    return false;
  }
}

// ── Send a single URL to /open (YouTube or aria2 dialog) ──
async function sendOpenDialog(url, kind) {
  if (!url) return false;
  const { connected, server } = await checkConnection(true);
  if (!connected || !server) {
    await notify("FelfelDM is not running!", 2);
    return false;
  }
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    const r = await fetch(`${server}/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, kind }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    if (r.ok) {
      notify(
        `Opening ${kind === "youtube" ? "YouTube" : "download"} dialog`,
      );
      return true;
    }
    return false;
  } catch (e) {
    console.error("sendOpenDialog error:", e);
    return false;
  }
}

// ── Download interception ──
browser.downloads.onCreated.addListener(async (item) => {
  if (!item.url || !item.url.startsWith("http")) return;
  if (!(await isCatchEnabled())) return;
  if (consumeIgnored(item.url)) return;

  const { connected } = await checkConnection(false);
  if (!connected) {
    console.log("⚠️ FelfelDM not connected, leaving download to browser");
    return;
  }

  const accepted = await send([item.url]);
  if (!accepted) {
    await notify(
      "FelfelDM did not accept the download.\nThe browser will handle it instead.",
    );
    return;
  }

  try {
    await browser.downloads.cancel(item.id);
  } catch (e) {
    console.error("Cancel error:", e);
  }
  setTimeout(async () => {
    try {
      await browser.downloads.erase({ id: item.id });
    } catch (e) {}
  }, 300);
});

// ── Context Menus ──
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
    if (browser.contextMenus.removeAll) await browser.contextMenus.removeAll();
    for (const item of MENU_ITEMS) browser.contextMenus.create(item);
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

// ── Selected links ──
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
    await notify("Download catching is disabled. Enable it from the popup.");
    return;
  }
  const { connected } = await checkConnection(false);
  if (!connected) {
    await notify("FelfelDM is not running!", 2);
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

// ── Message handling ──
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "toggle_catch") {
    updateBadge();
    return;
  }
  if (message.action === "add_urls") {
    send(message.urls).then((result) =>
      sendResponse({ status: result ? "success" : "error" }),
    );
    return true;
  }
  if (message.action === "open_dialog") {
    sendOpenDialog(message.url, message.kind || "download").then((result) => {
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
  // Best captured media URL for the asking tab. `mediaType` is "audio" or
  // "video"; the answer's `kind` is "file" (aria2 can fetch it) or
  // "manifest" (HLS/DASH, needs yt-dlp).
  if (message.action === "get_media_url") {
    const tabId = sender?.tab?.id;
    if (tabId === undefined) {
      sendResponse({ url: null });
      return true;
    }
    serialize(() => readTab(tabId))
      .then((state) => sendResponse(pickBest(state.items, message.mediaType)))
      .catch(() => sendResponse({ url: null }));
    return true;
  }
});

// Warm up on load.
createContextMenus();
ensureRefreshAlarm();
checkConnection(true);
