const INSTALL_FLAG = "__DESKPILOT_CONTENT_INSTALLED__";
const globalState = globalThis as typeof globalThis & Record<string, boolean>;

if (!globalState[INSTALL_FLAG]) {
  globalState[INSTALL_FLAG] = true;

  function collectVisibleText(maxChars: number): string {
    return document.body?.innerText?.slice(0, maxChars) ?? "";
  }

  function collectDomSummary() {
    return Array.from(document.querySelectorAll("h1,h2,h3,button,a,input,textarea,select"))
      .slice(0, 200)
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        text: (element.textContent ?? "").trim().slice(0, 120),
        ariaLabel: element.getAttribute("aria-label"),
        role: element.getAttribute("role"),
      }));
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "DESKPILOT_COLLECT_PAGE") {
      return false;
    }
    const maxTextChars = Number(message.payload?.max_text_chars ?? 30000);
    sendResponse({
      url: location.href,
      title: document.title,
      visible_text: collectVisibleText(maxTextChars),
      dom_summary: collectDomSummary(),
      captured_at: new Date().toISOString(),
    });
    return true;
  });
}
