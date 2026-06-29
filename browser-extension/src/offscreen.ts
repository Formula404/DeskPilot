const WS_URL = "ws://127.0.0.1:8765/browser/ws";
const HEARTBEAT_MS = 20_000;
const RECONNECT_MS = 1_000;

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

let socket: WebSocket | null = null;
let reconnectTimer: number | undefined;
let heartbeatTimer: number | undefined;

function sendToBackend(message: unknown) {
  if (socket?.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify(message));
}

function registerBrowser() {
  sendToBackend({
    type: "browser.register",
    client_id: chrome.runtime.id,
    browser: "chromium",
    capabilities: ["collect_page"],
  });
}

function startHeartbeat() {
  if (heartbeatTimer !== undefined) {
    self.clearInterval(heartbeatTimer);
  }
  heartbeatTimer = self.setInterval(() => {
    sendToBackend({
      type: "browser.ping",
      sent_at: new Date().toISOString(),
    });
  }, HEARTBEAT_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer === undefined) return;
  self.clearInterval(heartbeatTimer);
  heartbeatTimer = undefined;
}

function scheduleReconnect(closedSocket: WebSocket) {
  if (socket !== closedSocket) return;
  stopHeartbeat();
  if (reconnectTimer !== undefined) return;
  reconnectTimer = self.setTimeout(() => {
    reconnectTimer = undefined;
    connect();
  }, RECONNECT_MS);
}

function connect() {
  if (
    socket &&
    (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)
  ) {
    return;
  }

  const nextSocket = new WebSocket(WS_URL);
  socket = nextSocket;
  nextSocket.addEventListener("open", () => {
    if (socket !== nextSocket) return;
    if (reconnectTimer !== undefined) {
      self.clearTimeout(reconnectTimer);
      reconnectTimer = undefined;
    }
    registerBrowser();
    startHeartbeat();
  });
  nextSocket.addEventListener("message", (event) => {
    if (socket !== nextSocket) return;
    void handleBackendMessage(event.data);
  });
  nextSocket.addEventListener("close", () => scheduleReconnect(nextSocket));
  nextSocket.addEventListener("error", () => scheduleReconnect(nextSocket));
}

async function executeCommand(command: BrowserCommand): Promise<BrowserResult> {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "DESKPILOT_EXECUTE_BROWSER_COMMAND",
      command,
    });
    return response as BrowserResult;
  } catch (error) {
    return {
      type: "browser.result",
      request_id: command.request_id,
      ok: false,
      command: command.command,
      data: null,
      error: {
        code: "BACKGROUND_UNAVAILABLE",
        message: error instanceof Error ? error.message : "浏览器后台执行器不可用。",
      },
    };
  }
}

async function handleBackendMessage(raw: string) {
  let message: Partial<BrowserCommand>;
  try {
    message = JSON.parse(raw) as Partial<BrowserCommand>;
  } catch {
    return;
  }
  if (message.type !== "browser.command" || !message.request_id || !message.command) {
    return;
  }
  const result = await executeCommand(message as BrowserCommand);
  sendToBackend(result);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "DESKPILOT_OFFSCREEN_CONNECT") {
    return false;
  }
  connect();
  sendResponse({ ok: true });
  return false;
});

connect();

export {};
