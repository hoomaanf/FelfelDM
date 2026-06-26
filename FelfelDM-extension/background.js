const SERVER = "http://localhost:8765";
const ICON_URL = browser.runtime.getURL("icons/icon128.png");

async function ping() {
  try {
    const r = await fetch(`${SERVER}/ping`);
    return r.ok;
  } catch {
    return false;
  }
}

async function send(urls) {
  const ok = await ping();

  if (!ok) {
    await browser.notifications.create({
      type: "basic",
      iconUrl: ICON_URL,
      title: "🌶️ FelfelDM",
      message: "FelfelDM is not running. Please open the app.",
    });

    return false;
  }

  try {
    const r = await fetch(`${SERVER}/add`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ urls }),
    });

    if (r.ok) {
      browser.notifications.create({
        type: "basic",
        iconUrl: ICON_URL,
        title: "🌶️ FelfelDM",
        message: `✅ Added ${urls.length} download(s)`,
      });
    }

    return r.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

const ignored = new Set();

browser.downloads.onCreated.addListener(async (item) => {
  if (!item.url.startsWith("http")) return;

  if (ignored.has(item.url)) {
    ignored.delete(item.url);
    return;
  }

  const sent = await send([item.url]);

  if (!sent) return;

  try {
    await browser.downloads.cancel(item.id);

    setTimeout(async () => {
      try {
        await browser.downloads.erase({
          id: item.id,
        });
      } catch {}
    }, 300);
  } catch (e) {
    console.error(e);
  }
});

browser.runtime.onInstalled.addListener(() => {
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
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  switch (info.menuItemId) {
    case "download-link":
      ignored.add(info.linkUrl);
      await send([info.linkUrl]);
      break;

    case "download-image":
      ignored.add(info.srcUrl);
      await send([info.srcUrl]);
      break;

    case "download-video":
      ignored.add(info.srcUrl);
      await send([info.srcUrl]);
      break;

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
        const links = await browser.tabs.sendMessage(tab.id, {
          type: "getSelectedLinks",
        });

        if (links && links.length) {
          await send(links);
        } else {
          browser.notifications.create({
            type: "basic",
            iconUrl: "icon.png",
            title: "FelfelDM",
            message: "No links found in selection.",
          });
        }
      } catch (e) {
        console.error(e);
      }

      break;
    }
  }
});

browser.contextMenus.create({
  id: "download-link",
  title: "Download with FelfelDM",
  contexts: ["link"],
});

browser.contextMenus.create({
  id: "download-selected-links",
  title: "Download Selected Links",
  contexts: ["selection"],
});
