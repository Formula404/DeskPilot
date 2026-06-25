const API_BASE = "http://127.0.0.1:8765";

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  const page = await chrome.tabs.sendMessage(tab.id, { type: "DESKPILOT_COLLECT_PAGE" });
  await fetch(`${API_BASE}/context/browser/current-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tab_id: tab.id,
      ...page
    })
  });
});
