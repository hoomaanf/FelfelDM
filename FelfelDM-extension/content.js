// content.js - For both Firefox and Chrome

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type !== "getSelectedLinks") {
    return;
  }

  const selection = window.getSelection();

  if (!selection || selection.rangeCount === 0) {
    return Promise.resolve([]);
  }

  const fragment = selection.getRangeAt(0).cloneContents();

  const urls = [
    ...new Set(
      [...fragment.querySelectorAll("a[href]")]
        .map((a) => a.href)
        .filter(Boolean),
    ),
  ];

  return Promise.resolve(urls);
});

// For Chrome: inject script for selected links
if (typeof browser === "undefined") {
  // Chrome fallback
  window.addEventListener("message", (event) => {
    if (event.data?.type === "getSelectedLinks") {
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) return;
      const fragment = selection.getRangeAt(0).cloneContents();
      const urls = [
        ...new Set(
          [...fragment.querySelectorAll("a[href]")]
            .map((a) => a.href)
            .filter(Boolean),
        ),
      ];
      window.postMessage({ type: "selectedLinks", urls });
    }
  });
}
