// content.js - Firefox only.
//
// Chrome doesn't have a native `browser` global, and this file has no
// polyfill, so it must not reference `browser` unconditionally or it
// throws on every page load in Chrome. Chrome gets selected-link URLs a
// different way (background.js injects a one-off function via
// chrome.scripting.executeScript), so it never needed anything from this
// file. The previous version's Chrome "fallback" listened for
// window.postMessage with no origin/source check, which any page could
// have used to read the user's current text selection's links - it was
// unused dead code, so it's removed outright rather than fixed.

if (typeof browser !== "undefined") {
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
}