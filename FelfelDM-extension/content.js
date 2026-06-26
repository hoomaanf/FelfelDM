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
