// FelfelDM content script — IDM-style "Download with FelfelDM" pill that
// sits on videos and next to audio players.
//
// Which link gets sent on click:
//   1. YouTube page      -> canonical video URL, kind "video" (yt-dlp dialog)
//   2. Element has a real http(s) src (progressive mp4/mp3/...) -> that URL
//      to the normal aria2 dialog
//   3. Element uses blob:/MSE/HLS -> best direct file the background script
//      captured on the network for this tab (normal dialog)
//   4. Only a manifest (m3u8/mpd) or nothing was seen -> page URL, kind ""
//      so the app decides (yt-dlp handles HLS pages such as Aparat)
(function () {
  "use strict";

  if (window.__felfelDmContentLoaded) return;
  window.__felfelDmContentLoaded = true;

  const api = globalThis.browser ?? globalThis.chrome;

  const STORAGE_KEY = "felfelDmHidden";
  const AUTO_COLLAPSE_MS = 4000;
  const SCAN_INTERVAL_MS = 3000;

  let hidden = false;
  try {
    hidden = sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch (e) {
    // sessionStorage can throw in sandboxed frames; treat as "not hidden".
  }
  if (hidden) return;

  // media element -> pill host element
  const panels = new Map();

  // ───────────────────────── URL helpers ─────────────────────────

  function isHttp(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u);
  }

  function isManifest(u) {
    return /\.(m3u8|mpd)(?:[?#]|$)/i.test(u);
  }

  // Returns { isYoutube, url }. `url` is null on YouTube pages that are not
  // a single video (home, search, channel...).
  function youtubeInfo() {
    const host = location.hostname.toLowerCase();
    const isYoutube =
      /(^|\.)youtube\.com$/.test(host) ||
      /(^|\.)youtube-nocookie\.com$/.test(host) ||
      host === "youtu.be";
    if (!isYoutube) return { isYoutube: false, url: null };

    const u = new URL(location.href);
    let id = null;
    let shorts = false;

    if (host === "youtu.be") {
      id = u.pathname.split("/")[1] || null;
    } else if (u.pathname === "/watch") {
      id = u.searchParams.get("v");
    } else {
      const m = u.pathname.match(
        /^\/(shorts|live|embed|v)\/([A-Za-z0-9_-]{6,})/,
      );
      if (m) {
        id = m[2];
        shorts = m[1] === "shorts";
      }
    }

    if (!id || !/^[A-Za-z0-9_-]{6,}$/.test(id)) {
      return { isYoutube: true, url: null };
    }

    const base =
      host === "music.youtube.com"
        ? "https://music.youtube.com"
        : "https://www.youtube.com";
    // Only the video id: drops &list=, &t=, &index= so a playlist link does
    // not turn into a whole-playlist download.
    const url = shorts ? `${base}/shorts/${id}` : `${base}/watch?v=${id}`;
    return { isYoutube: true, url };
  }

  // Sites (besides YouTube) where one page = one video, matched by host and
  // path so feeds and home pages never send the wrong URL. Returns the
  // canonical page URL (no query/hash) or null.
  const SITE_VIDEO_PATTERNS = [
    [/(^|\.)vimeo\.com$/, /^\/(\d+|channels\/[^/]+\/\d+|groups\/[^/]+\/videos\/\d+)/],
    [/(^|\.)dailymotion\.com$/, /^\/video\//],
    [/(^|\.)twitch\.tv$/, /^\/(videos\/\d+|[^/]+\/clip\/)/],
    [/(^|\.)tiktok\.com$/, /^\/@[^/]+\/video\/\d+/],
    [/(^|\.)(twitter|x)\.com$/, /^\/[^/]+\/status\/\d+/],
    [/(^|\.)instagram\.com$/, /^\/(p|reel|reels|tv)\/[^/]+/],
    [/(^|\.)rumble\.com$/, /^\/v[^/]+/],
    [/(^|\.)streamable\.com$/, /^\/[a-z0-9]+$/i],
    [/(^|\.)bilibili\.com$/, /^\/video\//],
    [/(^|\.)reddit\.com$/, /^\/r\/[^/]+\/comments\//],
  ];

  function siteVideoUrl() {
    const host = location.hostname.toLowerCase();
    for (const [hostRe, pathRe] of SITE_VIDEO_PATTERNS) {
      if (hostRe.test(host) && pathRe.test(location.pathname)) {
        return location.origin + location.pathname;
      }
    }
    return null;
  }

  // The element's own downloadable URL, or null for blob:/MSE players.
  function ownUrl(media) {
    const cands = [media.currentSrc, media.src];
    media.querySelectorAll("source[src]").forEach((s) => cands.push(s.src));
    return cands.find(isHttp) || null;
  }

  // ───────────────────────── Messaging ─────────────────────────

  function sendToBackground(message) {
    try {
      const p = api.runtime.sendMessage(message);
      if (p && typeof p.catch === "function") p.catch(() => {});
      return Promise.resolve(p);
    } catch (e) {
      console.warn("FelfelDM: sendMessage failed", e);
      return Promise.resolve(undefined);
    }
  }

  async function onDownload(media) {
    const yt = youtubeInfo();
    if (yt.isYoutube) {
      if (yt.url) {
        sendToBackground({
          action: "open_dialog",
          url: yt.url,
          kind: "video",
        });
      }
      return;
    }

    // Other yt-dlp sites whose page URL *is* the video: let yt-dlp handle it
    // instead of grabbing a raw (often split or protected) stream.
    const site = siteVideoUrl();
    if (site) {
      sendToBackground({ action: "open_dialog", url: site, kind: "video" });
      return;
    }

    const mediaType = media.tagName === "AUDIO" ? "audio" : "video";

    // 1. The element itself points at a real file.
    const own = ownUrl(media);
    if (own && !isManifest(own)) {
      sendToBackground({ action: "add_urls", urls: [own] });
      return;
    }

    // 2. blob:/MSE player: use what the network layer saw for this tab.
    try {
      const resp = await sendToBackground({
        action: "get_media_url",
        mediaType,
      });
      if (resp && resp.url && resp.kind === "file") {
        sendToBackground({ action: "add_urls", urls: [resp.url] });
        return;
      }
    } catch (err) {
      console.warn("FelfelDM: get_media_url failed", err);
    }

    // 3. Only a manifest (or nothing): let the app decide from the page URL.
    sendToBackground({ action: "open_dialog", url: location.href, kind: "" });
  }

  // ───────────────────────── Eligibility ─────────────────────────

  // requireVisible: must intersect the viewport (used when attaching; an
  // already-attached pill is kept while the media scrolls out of view).
  function eligible(media, requireVisible) {
    const isAudio = media.tagName === "AUDIO";
    const r = media.getBoundingClientRect();

    if (isAudio) {
      if (r.width < 60 || r.height < 20) return false; // hidden/custom player
    } else if (r.width < 100 || r.height < 50) {
      return false;
    }

    if (requireVisible) {
      if (
        r.bottom <= 0 ||
        r.top >= window.innerHeight ||
        r.right <= 0 ||
        r.left >= window.innerWidth
      ) {
        return false;
      }
    }

    const yt = youtubeInfo();
    if (yt.isYoutube) {
      // Not a single-video page, or a hover preview / thumbnail player:
      // the page URL would be the wrong video.
      if (!yt.url) return false;
      if (r.width < 240) return false;
      if (
        media.closest(
          "ytd-video-preview, ytd-thumbnail, ytd-rich-grid-media, ytd-compact-video-renderer",
        )
      ) {
        return false;
      }
    }
    return true;
  }

  // ───────────────────────── Pill UI ─────────────────────────

  const PILL_CSS = `
    :host { all: initial; }
    .pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      height: 36px;
      padding: 0 10px 0 4px;
      border-radius: 18px;
      background: rgba(28, 28, 30, 0.88);
      -webkit-backdrop-filter: blur(12px) saturate(180%);
      backdrop-filter: blur(12px) saturate(180%);
      border: 1px solid rgba(255, 255, 255, 0.15);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
      color: #fff;
      font: 500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      white-space: nowrap;
      cursor: pointer;
      overflow: hidden;
      user-select: none;
      transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .ico {
      width: 28px; height: 28px; flex: none;
      display: flex; align-items: center; justify-content: center;
    }
    .ico img { width: 20px; height: 20px; display: block; pointer-events: none; }
    .label {
      display: inline-block; max-width: 200px; margin: 0 4px; opacity: 1;
      transition: all 0.35s ease;
    }
    .x {
      flex: none; width: 22px; height: 22px; margin-left: 4px; padding: 0;
      display: flex; align-items: center; justify-content: center;
      border: none; border-radius: 50%; background: transparent;
      color: rgba(255, 255, 255, 0.55);
      font: 300 18px/1 sans-serif; cursor: pointer; opacity: 1;
      transition: all 0.2s ease;
    }
    .x:hover { color: #fff; background: rgba(255, 255, 255, 0.15); }
    .pill.collapsed { width: 32px; height: 32px; padding: 0; opacity: 0.7; }
    .pill.collapsed .label,
    .pill.collapsed .x { opacity: 0; max-width: 0; width: 0; margin: 0; }
  `;

  function hideAll() {
    hidden = true;
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch (e) {}
    panels.forEach((host) => host.remove());
    panels.clear();
  }

  function createPanel(media) {
    const isAudio = media.tagName === "AUDIO";

    const host = document.createElement("div");
    host.className = "felfel-dm-fab";
    host.style.cssText = isAudio
      ? "all: initial; display: inline-block; vertical-align: middle; margin: 0 8px; position: relative; z-index: 2147483647;"
      : "all: initial; display: block; position: fixed; top: 0; right: 0; z-index: 2147483647;";

    const shadow = host.attachShadow({ mode: "closed" });

    const style = document.createElement("style");
    style.textContent = PILL_CSS;
    shadow.appendChild(style);

    const pill = document.createElement("div");
    pill.className = "pill";
    pill.title = "Download with FelfelDM";

    const ico = document.createElement("div");
    ico.className = "ico";
    const img = document.createElement("img");
    try {
      img.src = api.runtime.getURL("icons/icon48.png");
    } catch (e) {}
    img.alt = "FelfelDM";
    // icons/ must be a web_accessible_resource; without it show a glyph.
    img.addEventListener("error", () => {
      img.remove();
      ico.textContent = "⬇";
    });
    ico.appendChild(img);
    pill.appendChild(ico);

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = "Download with FelfelDM";
    pill.appendChild(label);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "x";
    closeBtn.textContent = "×";
    closeBtn.title = "Hide on this site for this session";
    closeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      hideAll();
    });
    pill.appendChild(closeBtn);

    shadow.appendChild(pill);

    // Auto-collapse to just the icon; expand on hover. Timer is per pill.
    let timer = null;
    const collapse = () => pill.classList.add("collapsed");
    const expand = () => pill.classList.remove("collapsed");
    timer = setTimeout(collapse, AUTO_COLLAPSE_MS);
    host.addEventListener("mouseenter", () => {
      clearTimeout(timer);
      expand();
    });
    host.addEventListener("mouseleave", () => {
      clearTimeout(timer);
      timer = setTimeout(collapse, AUTO_COLLAPSE_MS);
    });

    pill.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      onDownload(media);
    });

    // Never let the pill toggle play/pause or open the page's own menus.
    [
      "mousedown",
      "mouseup",
      "pointerdown",
      "pointerup",
      "dblclick",
      "contextmenu",
    ].forEach((ev) => host.addEventListener(ev, (e) => e.stopPropagation()));

    return host;
  }

  const PILL_H = 36;
  const PILL_GAP = 6;

  // Root the video pill lives under: <html>, or the fullscreen element when
  // the player is fullscreen (anything outside it is not rendered then).
  function hostRoot(media) {
    const fs = document.fullscreenElement;
    return fs && fs !== media && fs.contains(media)
      ? fs
      : document.documentElement;
  }

  // Video pills are position:fixed, OUTSIDE the player, just above its
  // top-right corner. With no room above (player flush with the top of the
  // viewport) or in fullscreen they fall back to the inside top-right corner.
  function place(host, media) {
    if (media.tagName === "AUDIO") return; // inline sibling, nothing to place
    const fs = document.fullscreenElement;
    if (fs === media) {
      // Children of a fullscreen <video> are never rendered.
      host.style.display = "none";
      return;
    }
    const de = document.documentElement;
    const mr = media.getBoundingClientRect();
    if (
      mr.bottom <= 0 ||
      mr.top >= de.clientHeight ||
      mr.right <= 0 ||
      mr.left >= de.clientWidth
    ) {
      host.style.display = "none"; // media scrolled out of view
      return;
    }
    host.style.display = "block";

    const right = Math.max(0, de.clientWidth - mr.right);
    const inFs = !!(fs && fs.contains(media));
    if (!inFs && mr.top >= PILL_H + PILL_GAP) {
      host.style.top = "auto";
      host.style.bottom = `${Math.round(de.clientHeight - mr.top + PILL_GAP)}px`;
      host.style.right = `${Math.round(right)}px`;
    } else {
      host.style.bottom = "auto";
      host.style.top = `${Math.round(Math.max(0, mr.top) + 12)}px`;
      host.style.right = `${Math.round(right + 12)}px`;
    }
  }

  function attach(media) {
    const host = createPanel(media);

    if (media.tagName === "AUDIO") {
      // Right beside the <audio> element.
      media.insertAdjacentElement("afterend", host);
    } else {
      hostRoot(media).appendChild(host);
      place(host, media);
    }
    panels.set(media, host);
  }

  // ───────────────────────── Scanning ─────────────────────────

  function scan() {
    if (hidden) return;

    for (const [media, host] of panels) {
      if (!host.isConnected) {
        // The page re-rendered and dropped our node: re-attach below.
        panels.delete(media);
      } else if (!media.isConnected || !eligible(media, false)) {
        host.remove();
        panels.delete(media);
      } else {
        place(host, media);
      }
    }

    document.querySelectorAll("video, audio").forEach((media) => {
      if (panels.has(media) || !eligible(media, true)) return;
      attach(media);
    });
  }

  let scanTimer = null;
  function scheduleScan(delay) {
    if (scanTimer) return;
    scanTimer = setTimeout(() => {
      scanTimer = null;
      scan();
    }, delay ?? 250);
  }

  let placeRaf = 0;
  function schedulePlace() {
    if (placeRaf) return;
    placeRaf = requestAnimationFrame(() => {
      placeRaf = 0;
      panels.forEach((h, m) => place(h, m));
    });
  }

  function onFullscreenChange() {
    panels.forEach((host, media) => {
      if (media.tagName === "AUDIO") return;
      const root = hostRoot(media);
      if (host.parentNode !== root) root.appendChild(host);
    });
    schedulePlace();
    scheduleScan();
  }

  function init() {
    scan();

    new MutationObserver(() => scheduleScan()).observe(
      document.documentElement,
      {
        childList: true,
        subtree: true,
      },
    );

    // Media becoming sized/playing, scrolling (YouTube Shorts), resizing,
    // fullscreen and YouTube's SPA navigation all change what is eligible.
    document.addEventListener("loadedmetadata", () => scheduleScan(), true);
    document.addEventListener("play", () => scheduleScan(), true);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    window.addEventListener(
      "scroll",
      () => {
        schedulePlace();
        scheduleScan(300);
      },
      { passive: true, capture: true },
    );
    window.addEventListener("resize", () => {
      schedulePlace();
      scheduleScan(300);
    });
    document.addEventListener("yt-navigate-finish", () => {
      setTimeout(scan, 300);
      setTimeout(scan, 1200);
    });

    setInterval(scan, SCAN_INTERVAL_MS);
  }

  init();
})();
