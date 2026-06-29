const API_BASE = "http://127.0.0.1:8765";

async function postCurrentPage(tabId: number) {
  const page = await chrome.tabs.sendMessage(tabId, { type: "DESKPILOT_COLLECT_PAGE" });
  await fetch(`${API_BASE}/context/browser/current-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tab_id: tabId,
      ...page
    })
  });
}

async function collectActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("http")) return;
  await postCurrentPage(tab.id);
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  await postCurrentPage(tab.id);
});

chrome.tabs.onActivated.addListener(async () => {
  await collectActiveTab();
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab.url?.startsWith("http")) return;
  await postCurrentPage(tabId);
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "DESKPILOT_PAGE_VISIBLE" || !sender.tab?.id) {
    return false;
  }
  void postCurrentPage(sender.tab.id);
  return false;
});
