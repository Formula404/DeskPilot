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

async function sendExtractTableMessage(tabId: number, payload: Record<string, unknown>) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: "DESKPILOT_EXTRACT_TABLE",
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
      type: "DESKPILOT_EXTRACT_TABLE",
      payload,
    });
  }
}

async function sendExtractStructuredBlocksMessage(tabId: number, payload: Record<string, unknown>) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: "DESKPILOT_EXTRACT_STRUCTURED_BLOCKS",
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
      type: "DESKPILOT_EXTRACT_STRUCTURED_BLOCKS",
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

async function collectMetadata(command: BrowserCommand) {
  const tab = await getTargetTab(command);
  if (!tab.id || !tab.url?.startsWith("http")) {
    throw new Error("当前标签页不是可读取的普通网页，请切换到 http/https 页面后重试。");
  }
  let selectionText = "";
  let contentHash = "";
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: async () => {
        const text = document.body?.innerText?.slice(0, 100000) ?? "";
        let hash = "";
        try {
          const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
          hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
        } catch {
          // The backend records an explicit degraded reason when a hash is unavailable.
        }
        return {
          selection_text: window.getSelection()?.toString().slice(0, 8000) ?? "",
          content_hash: hash,
        };
      },
    });
    selectionText = String(results[0]?.result?.selection_text ?? "");
    contentHash = String(results[0]?.result?.content_hash ?? "");
  } catch {
    // Restricted pages can still provide stable tab metadata.
  }
  return {
    tab_id: tab.id,
    url: tab.url,
    title: tab.title ?? "",
    document_id: `${tab.id}:${tab.url}`,
    content_hash: contentHash || undefined,
    selection_text: selectionText,
    captured_at: new Date().toISOString(),
  };
}

async function extractTable(command: BrowserCommand) {
  const tab = await getTargetTab(command);
  if (!tab.id || !tab.url?.startsWith("http")) {
    throw new Error("当前标签页不是可读取的普通网页，请切换到 http/https 页面后重试。");
  }
  const tables = await sendExtractTableMessage(tab.id, command.payload ?? {});
  return {
    tab_id: tab.id,
    ...tables,
  };
}

async function extractStructuredBlocks(command: BrowserCommand) {
  const tab = await getTargetTab(command);
  if (!tab.id || !tab.url?.startsWith("http")) {
    throw new Error("当前标签页不是可读取的普通网页，请切换到 http/https 页面后重试。");
  }
  const blocks = await sendExtractStructuredBlocksMessage(tab.id, command.payload ?? {});
  return {
    tab_id: tab.id,
    ...blocks,
  };
}

async function handleCommand(command: BrowserCommand): Promise<BrowserResult> {
  try {
    if (!["collect_metadata", "collect_page", "extract_table", "extract_structured_blocks"].includes(command.command)) {
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

    let data: unknown;
    if (command.command === "collect_metadata") {
      data = await collectMetadata(command);
    } else if (command.command === "collect_page") {
      data = await collectPage(command);
    } else if (command.command === "extract_table") {
      data = await extractTable(command);
    } else {
      data = await extractStructuredBlocks(command);
    }
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
