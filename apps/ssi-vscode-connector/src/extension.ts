import * as vscode from "vscode";

/**
 * SSI Connector — connects the IDE to a company's private SSI
 * (Sovereign Super Intelligence) endpoint.
 *
 * The SSI control layer runs the only agent loop. This extension:
 *   - checks the control layer health route,
 *   - shows connection state in the status bar,
 *   - keeps the bearer token in VS Code Secret Storage,
 *   - produces mcp.json snippets for the business and engineering MCP gateways.
 * MCP slots never talk to each other; the control layer is what combines results.
 */

const TOKEN_SECRET_KEY = "ssi.token";
const HEALTH_ROUTE = "/healthz";
const HEALTH_TIMEOUT_MS = 8000;

interface SsiConfig {
  endpoint: string;
  controlPath: string;
  businessMcpPath: string;
  engineeringMcpPath: string;
  showStatusBar: boolean;
}

type Status = "disconnected" | "connected" | "error";

interface ConnectionState {
  status: Status;
  lastChecked?: Date;
  message?: string;
}

let statusBarItem: vscode.StatusBarItem | undefined;
let output: vscode.OutputChannel | undefined;
let secrets: vscode.SecretStorage | undefined;
let state: ConnectionState = { status: "disconnected" };

// ---------- config + URLs ----------

function normalizePath(p: string | undefined, fallback: string): string {
  const v = (p ?? "").trim() || fallback;
  const withSlash = v.startsWith("/") ? v : `/${v}`;
  return withSlash.replace(/\/+$/, "");
}

function readConfig(): SsiConfig {
  const cfg = vscode.workspace.getConfiguration("ssi");
  return {
    endpoint: (cfg.get<string>("endpoint") || "").trim().replace(/\/+$/, ""),
    controlPath: normalizePath(cfg.get<string>("controlPath"), "/control"),
    businessMcpPath: normalizePath(cfg.get<string>("businessMcpPath"), "/mcp/business"),
    engineeringMcpPath: normalizePath(cfg.get<string>("engineeringMcpPath"), "/mcp/engineering"),
    showStatusBar: cfg.get<boolean>("showStatusBar") !== false,
  };
}

function healthUrl(cfg: SsiConfig): string {
  return `${cfg.endpoint}${cfg.controlPath}${HEALTH_ROUTE}`;
}

function mcpUrls(cfg: SsiConfig): { business: string; engineering: string } {
  return {
    business: `${cfg.endpoint}${cfg.businessMcpPath}`,
    engineering: `${cfg.endpoint}${cfg.engineeringMcpPath}`,
  };
}

function validateEndpoint(value: string): string | undefined {
  const v = value.trim();
  if (!v) {
    return "Enter the SSI base URL, e.g. https://ssi.corp.example";
  }
  try {
    const u = new URL(v);
    if (u.protocol !== "https:" && u.protocol !== "http:") {
      return "Use an https:// URL.";
    }
    if (u.search || u.hash) {
      return "Enter only the base URL (no query string or #fragment).";
    }
  } catch {
    return "Not a valid URL. Example: https://ssi.corp.example";
  }
  return undefined;
}

// ---------- token (Secret Storage) ----------

async function getToken(): Promise<string | undefined> {
  const t = await secrets?.get(TOKEN_SECRET_KEY);
  return t && t.trim() ? t.trim() : undefined;
}

/** One-time move of a legacy plain-text ssi.token setting into Secret Storage. */
async function migrateLegacyToken(): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("ssi");
  const inspected = cfg.inspect<string>("token");
  const legacy =
    (inspected?.workspaceFolderValue || inspected?.workspaceValue || inspected?.globalValue || "").trim();
  if (!legacy) {
    return;
  }
  if (!(await getToken())) {
    await secrets?.store(TOKEN_SECRET_KEY, legacy);
  }
  const targets: Array<[unknown, vscode.ConfigurationTarget]> = [
    [inspected?.globalValue, vscode.ConfigurationTarget.Global],
    [inspected?.workspaceValue, vscode.ConfigurationTarget.Workspace],
    [inspected?.workspaceFolderValue, vscode.ConfigurationTarget.WorkspaceFolder],
  ];
  for (const [val, target] of targets) {
    if (val !== undefined) {
      try {
        await cfg.update("token", undefined, target);
      } catch (err) {
        log(`Could not clear legacy ssi.token at target ${target}: ${errMsg(err)}`);
      }
    }
  }
  log("Moved legacy ssi.token setting into Secret Storage and removed it from settings.");
  void vscode.window.showInformationMessage(
    "SSI: your token was moved from settings into VS Code Secret Storage."
  );
}

async function setTokenCommand(): Promise<boolean> {
  const token = await vscode.window.showInputBox({
    title: "SSI: Set Token",
    prompt: "Bearer token for your SSI endpoint. Stored in VS Code Secret Storage, not in settings.",
    password: true,
    ignoreFocusOut: true,
    validateInput: (v) => (v.trim() ? undefined : "Token cannot be empty (use SSI: Clear Token to remove it)."),
  });
  if (token === undefined) {
    return false;
  }
  await secrets?.store(TOKEN_SECRET_KEY, token.trim());
  void vscode.window.showInformationMessage("SSI token saved to Secret Storage.");
  return true;
}

async function clearTokenCommand(): Promise<void> {
  await secrets?.delete(TOKEN_SECRET_KEY);
  void vscode.window.showInformationMessage("SSI token removed from Secret Storage.");
}

// ---------- status bar ----------

function updateStatusBar(): void {
  if (!statusBarItem) {
    return;
  }
  const cfg = readConfig();
  if (!cfg.showStatusBar) {
    statusBarItem.hide();
    return;
  }
  switch (state.status) {
    case "connected":
      statusBarItem.text = "$(check) SSI: Connected";
      statusBarItem.tooltip = `SSI control layer healthy\n${cfg.endpoint}\nClick for status`;
      statusBarItem.backgroundColor = undefined;
      statusBarItem.command = "ssi.showStatus";
      break;
    case "error":
      statusBarItem.text = "$(error) SSI: Error";
      statusBarItem.tooltip = `${state.message ?? "Health check failed"}\nClick to retry`;
      statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
      statusBarItem.command = "ssi.connect";
      break;
    default:
      statusBarItem.text = "$(plug) SSI: Disconnected";
      statusBarItem.tooltip = "Click to connect to your SSI endpoint";
      statusBarItem.backgroundColor = undefined;
      statusBarItem.command = "ssi.connect";
  }
  statusBarItem.show();
}

// ---------- health probe ----------

async function probeHealth(cfg: SsiConfig, token: string | undefined): Promise<{ ok: boolean; detail: string }> {
  const url = healthUrl(cfg);
  const headers: Record<string, string> = { Accept: "text/plain, application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { method: "GET", headers, signal: controller.signal });
    if (res.ok) {
      return { ok: true, detail: `GET ${url} → ${res.status}` };
    }
    switch (res.status) {
      case 401:
      case 403:
        return {
          ok: false,
          detail: `GET ${url} → ${res.status}. The SSI endpoint rejected the token. Run "SSI: Set Token" with a valid token.`,
        };
      case 404:
        return {
          ok: false,
          detail: `GET ${url} → 404. The host answered but no control layer health route is there. Check ssi.controlPath (default /control) with your SSI administrator.`,
        };
      case 502:
      case 503:
      case 504:
        return {
          ok: false,
          detail: `GET ${url} → ${res.status}. The gateway is up but the SSI control layer is not responding.`,
        };
      default:
        return { ok: false, detail: `GET ${url} → ${res.status} ${res.statusText}`.trim() };
    }
  } catch (err) {
    if (controller.signal.aborted) {
      return {
        ok: false,
        detail: `Timed out after ${HEALTH_TIMEOUT_MS / 1000}s reaching ${url}. Make sure you are on your company's private network (VPN / Private Link).`,
      };
    }
    const cause = (err as { cause?: { code?: string; message?: string } })?.cause;
    const code = cause?.code ? ` (${cause.code})` : "";
    let hint = "Make sure you are on your company's private network (VPN / Private Link).";
    if (cause?.code === "ENOTFOUND" || cause?.code === "EAI_AGAIN") {
      hint = "The hostname did not resolve. Check ssi.endpoint and that you are on the private network / internal DNS.";
    } else if (cause?.code && /CERT|SELF_SIGNED|UNABLE_TO_VERIFY/.test(cause.code)) {
      hint = "TLS certificate was not trusted. Your company's CA may need to be installed on this machine.";
    }
    return {
      ok: false,
      detail: `Cannot reach ${url}${code}: ${cause?.message || errMsg(err)}. ${hint}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

// ---------- commands ----------

async function ensureEndpoint(): Promise<SsiConfig | undefined> {
  let cfg = readConfig();
  if (cfg.endpoint) {
    const bad = validateEndpoint(cfg.endpoint);
    if (bad) {
      void vscode.window.showErrorMessage(`SSI: ssi.endpoint "${cfg.endpoint}" is invalid. ${bad}`);
      return undefined;
    }
    return cfg;
  }
  const entered = await vscode.window.showInputBox({
    title: "SSI: Connect",
    prompt: "Base URL of your company's private SSI endpoint",
    placeHolder: "https://ssi.corp.example",
    ignoreFocusOut: true,
    validateInput: validateEndpoint,
  });
  if (!entered) {
    return undefined;
  }
  await vscode.workspace
    .getConfiguration("ssi")
    .update("endpoint", entered.trim().replace(/\/+$/, ""), vscode.ConfigurationTarget.Global);
  cfg = readConfig();
  return cfg;
}

async function connectCommand(): Promise<void> {
  const cfg = await ensureEndpoint();
  if (!cfg) {
    return;
  }

  let token = await getToken();
  if (!token) {
    const choice = await vscode.window.showInformationMessage(
      "No SSI token is set. Set one now, or continue without a token (only if your private gateway does not require one).",
      "Set Token",
      "Continue Without Token"
    );
    if (choice === "Set Token") {
      if (!(await setTokenCommand())) {
        return;
      }
      token = await getToken();
    } else if (choice !== "Continue Without Token") {
      return;
    }
  }

  const health = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: "SSI: checking control layer…" },
    () => probeHealth(cfg, token)
  );
  state = {
    status: health.ok ? "connected" : "error",
    lastChecked: new Date(),
    message: health.detail,
  };
  updateStatusBar();
  log(`[connect] ${health.detail}`);

  if (health.ok) {
    const choice = await vscode.window.showInformationMessage(
      `SSI connected: control layer at ${cfg.endpoint} is healthy. Run "SSI: Copy MCP Config" to add the business and engineering MCP gateways to your IDE agent.`,
      "Copy MCP Config",
      "Show Status"
    );
    if (choice === "Copy MCP Config") {
      await copyMcpConfigCommand();
    } else if (choice === "Show Status") {
      await showStatusCommand();
    }
  } else {
    const choice = await vscode.window.showErrorMessage(`SSI connection failed. ${health.detail}`, "Retry", "Open Settings", "Set Token");
    if (choice === "Retry") {
      await connectCommand();
    } else if (choice === "Open Settings") {
      await vscode.commands.executeCommand("workbench.action.openSettings", "ssi.");
    } else if (choice === "Set Token") {
      await setTokenCommand();
    }
  }
}

async function disconnectCommand(): Promise<void> {
  state = { status: "disconnected" };
  updateStatusBar();
  void vscode.window.showInformationMessage(
    "SSI disconnected in this window. Your token and any MCP entries in mcp.json are unchanged."
  );
}

async function showStatusCommand(): Promise<void> {
  const cfg = readConfig();
  const token = await getToken();
  const urls = cfg.endpoint ? mcpUrls(cfg) : undefined;
  const label = { connected: "Connected", error: "Error", disconnected: "Disconnected" }[state.status];
  const lines = [
    "# SSI Connector",
    "",
    "Sovereign Super Intelligence (SSI). The control layer is the only agent loop; the business and engineering MCP gateways are separate slots that never talk to each other.",
    "",
    `- **Status:** ${label}`,
    `- **Endpoint:** ${cfg.endpoint || "(not set — run SSI: Connect)"}`,
    `- **Token:** ${token ? "set (Secret Storage)" : "not set — run SSI: Set Token"}`,
    `- **Control layer health:** ${cfg.endpoint ? healthUrl(cfg) : "(set ssi.endpoint)"}`,
    `- **Business MCP:** ${urls?.business ?? "(set ssi.endpoint)"}`,
    `- **Engineering MCP:** ${urls?.engineering ?? "(set ssi.endpoint)"}`,
  ];
  if (state.lastChecked) {
    lines.push(`- **Last check:** ${state.lastChecked.toLocaleString()}`);
  }
  if (state.message) {
    lines.push(`- **Detail:** ${state.message}`);
  }
  const doc = await vscode.workspace.openTextDocument({ content: lines.join("\n") + "\n", language: "markdown" });
  await vscode.window.showTextDocument(doc, { preview: true });
}

const TOKEN_PLACEHOLDER = "Bearer <SSI_TOKEN>";

function buildMcpConfig(cfg: SsiConfig, flavor: "vscode" | "cursor", authValue: string): string {
  const urls = mcpUrls(cfg);
  const headers = { Authorization: authValue };
  if (flavor === "vscode") {
    return JSON.stringify(
      {
        servers: {
          "ssi-business": { type: "http", url: urls.business, headers },
          "ssi-engineering": { type: "http", url: urls.engineering, headers },
        },
      },
      null,
      2
    );
  }
  return JSON.stringify(
    {
      mcpServers: {
        "ssi-business": { url: urls.business, headers },
        "ssi-engineering": { url: urls.engineering, headers },
      },
    },
    null,
    2
  );
}

async function copyMcpConfigCommand(): Promise<void> {
  const cfg = readConfig();
  if (!cfg.endpoint) {
    void vscode.window.showErrorMessage('SSI: set ssi.endpoint first (run "SSI: Connect").');
    return;
  }

  const flavorPick = await vscode.window.showQuickPick(
    [
      {
        label: "VS Code",
        description: ".vscode/mcp.json — \"servers\" with type http",
        flavor: "vscode" as const,
      },
      {
        label: "Cursor",
        description: ".cursor/mcp.json — \"mcpServers\"",
        flavor: "cursor" as const,
      },
    ],
    { title: "SSI: Copy MCP Config", placeHolder: "Which IDE is this config for?" }
  );
  if (!flavorPick) {
    return;
  }

  let authValue = TOKEN_PLACEHOLDER;
  const token = await getToken();
  if (token) {
    const tokenPick = await vscode.window.showQuickPick(
      [
        { label: "Use placeholder", description: `Authorization: ${TOKEN_PLACEHOLDER} (recommended)`, include: false },
        { label: "Include my token", description: "Puts your real bearer token on the clipboard", include: true },
      ],
      { title: "SSI: Copy MCP Config", placeHolder: "Include your token in the copied JSON?" }
    );
    if (!tokenPick) {
      return;
    }
    if (tokenPick.include) {
      const confirm = await vscode.window.showWarningMessage(
        "Your SSI token will be copied to the clipboard in plain text. Do not commit an mcp.json that contains it.",
        { modal: true },
        "Copy With Token"
      );
      if (confirm !== "Copy With Token") {
        return;
      }
      authValue = `Bearer ${token}`;
    }
  }

  await vscode.env.clipboard.writeText(buildMcpConfig(cfg, flavorPick.flavor, authValue) + "\n");
  const file = flavorPick.flavor === "vscode" ? ".vscode/mcp.json" : ".cursor/mcp.json (or ~/.cursor/mcp.json)";
  const tail =
    authValue === TOKEN_PLACEHOLDER ? ` Replace ${TOKEN_PLACEHOLDER.replace("Bearer ", "")} with your token.` : "";
  void vscode.window.showInformationMessage(`SSI MCP config for ${flavorPick.label} copied. Paste or merge it into ${file}.${tail}`);
}

// ---------- helpers ----------

function log(line: string): void {
  output?.appendLine(`[${new Date().toISOString()}] ${line}`);
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// ---------- activation ----------

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  secrets = context.secrets;
  output = vscode.window.createOutputChannel("SSI Connector");
  statusBarItem = vscode.window.createStatusBarItem("ssi.status", vscode.StatusBarAlignment.Left, 100);
  statusBarItem.name = "SSI Connector";
  context.subscriptions.push(output, statusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand("ssi.connect", connectCommand),
    vscode.commands.registerCommand("ssi.disconnect", disconnectCommand),
    vscode.commands.registerCommand("ssi.setToken", setTokenCommand),
    vscode.commands.registerCommand("ssi.clearToken", clearTokenCommand),
    vscode.commands.registerCommand("ssi.showStatus", showStatusCommand),
    vscode.commands.registerCommand("ssi.copyMcpConfig", copyMcpConfigCommand),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("ssi.endpoint") || e.affectsConfiguration("ssi.controlPath")) {
        state = { status: "disconnected" };
      }
      if (e.affectsConfiguration("ssi")) {
        updateStatusBar();
      }
    })
  );

  try {
    await migrateLegacyToken();
  } catch (err) {
    log(`Token migration failed: ${errMsg(err)}`);
  }
  updateStatusBar();
}

export function deactivate(): void {
  statusBarItem = undefined;
  output = undefined;
  secrets = undefined;
}
