function collectVisibleText(): string {
  return document.body?.innerText?.slice(0, 30000) ?? "";
}

function collectDomSummary() {
  return Array.from(document.querySelectorAll("h1,h2,h3,button,a,input,textarea,select"))
    .slice(0, 200)
    .map((element) => ({
      tag: element.tagName.toLowerCase(),
      text: (element.textContent ?? "").trim().slice(0, 120),
      ariaLabel: element.getAttribute("aria-label"),
      role: element.getAttribute("role")
    }));
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "DESKPILOT_COLLECT_PAGE") {
    return false;
  }
  sendResponse({
    url: location.href,
    title: document.title,
    visible_text: collectVisibleText(),
    dom_summary: collectDomSummary(),
    captured_at: new Date().toISOString()
  });
  return true;
});

function notifyPageVisible() {
  if (document.visibilityState !== "visible") return;
  chrome.runtime.sendMessage({ type: "DESKPILOT_PAGE_VISIBLE" });
}

window.addEventListener("focus", notifyPageVisible);
document.addEventListener("visibilitychange", notifyPageVisible);
