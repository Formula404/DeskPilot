const OFFSCREEN_URL = "offscreen.html";

type BrowserCommand = {
  type: "browser.command";
  request_id: string;
  command: string;
  target?: { tab?: "active" | number };
  payload?: Record<string, unknown>;
};

type BrowserResult = {
  type: "browser.result";
  request_id: string;
  ok: boolean;
  command: string;
  data: unknown;
  error: { code: string; message: string; detail?: Record<string, unknown> } | null;
};

let creatingOffscreen: Promise<void> | null = null;

async function hasOffscreenDocument() {
  const offscreenUrl = chrome.runtime.getURL(OFFSCREEN_URL);
  const runtime = chrome.runtime as typeof chrome.runtime & {
    getContexts: (filter: {
      contextTypes: string[];
      documentUrls: string[];
    }) => Promise<Array<{ documentUrl?: string }>>;
  };
  const contexts = await runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [offscreenUrl],
  });
  return contexts.length > 0;
}

async function ensureOffscreenDocument() {
  if (await hasOffscreenDocument()) return;
  if (!creatingOffscreen) {
    creatingOffscreen = chrome.offscreen.createDocument({
      url: OFFSCREEN_URL,
      reasons: [chrome.offscreen.Reason.WORKERS],
      justification: "Maintain the DeskPilot local browser bridge WebSocket.",
    });
  }
  try {
    await creatingOffscreen;
  } finally {
    creatingOffscreen = null;
  }
}

async function wakeBridge() {
  await ensureOffscreenDocument();
  await chrome.runtime.sendMessage({ type: "DESKPILOT_OFFSCREEN_CONNECT" });
}

async function getTargetTab(command: BrowserCommand): Promise<chrome.tabs.Tab> {
  const targetTab = command.target?.tab;
  if (typeof targetTab === "number") {
    const tab = await chrome.tabs.get(targetTab);
    if (!tab.id) throw new Error("目标标签页不可用。");
    return tab;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("未找到当前活动标签页。");
  return tab;
}

async function sendCollectPageMessage(tabId: number, payload: Record<string, unknown>) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: "DESKPILOT_COLLECT_PAGE",
      payload,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.includes("Receiving end does not exist")) {
      throw error;
    }
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    return await chrome.tabs.sendMessage(tabId, {
      type: "DESKPILOT_COLLECT_PAGE",
      payload,
    });
  }
}

async function collectPage(command: BrowserCommand) {
  const tab = await getTargetTab(command);
  if (!tab.id || !tab.url?.startsWith("http")) {
    throw new Error("当前标签页不是可读取的普通网页，请切换到 http/https 页面后重试。");
  }
  const page = await sendCollectPageMessage(tab.id, command.payload ?? {});
  return {
    tab_id: tab.id,
    ...page,
  };
}

async function handleCommand(command: BrowserCommand): Promise<BrowserResult> {
  try {
    if (command.command !== "collect_page") {
      return {
        type: "browser.result",
        request_id: command.request_id,
        ok: false,
        command: command.command,
        data: null,
        error: {
          code: "UNSUPPORTED_COMMAND",
          message: `不支持的浏览器命令：${command.command}`,
        },
      };
    }

    const data = await collectPage(command);
    return {
      type: "browser.result",
      request_id: command.request_id,
      ok: true,
      command: command.command,
      data,
      error: null,
    };
  } catch (error) {
    return {
      type: "browser.result",
      request_id: command.request_id,
      ok: false,
      command: command.command,
      data: null,
      error: {
        code: "COMMAND_FAILED",
        message: error instanceof Error ? error.message : "浏览器命令执行失败。",
      },
    };
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "DESKPILOT_EXECUTE_BROWSER_COMMAND") {
    return false;
  }
  void handleCommand(message.command as BrowserCommand).then(sendResponse);
  return true;
});

chrome.runtime.onStartup.addListener(() => {
  void wakeBridge();
});
chrome.runtime.onInstalled.addListener(() => {
  void wakeBridge();
});
chrome.tabs.onActivated.addListener(() => {
  void wakeBridge();
});
chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.status === "complete") void wakeBridge();
});
chrome.action.onClicked.addListener(() => {
  void wakeBridge();
});

void wakeBridge();

export {};
