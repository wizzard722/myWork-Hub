/** Aanroepen naar de core. Het toegangstoken staat alleen in het geheugen; de
 *  refresh-sessie zit in een httpOnly-cookie die de browser zelf meestuurt. */

export type Role = "owner" | "admin" | "member";

export interface Theme {
  name: string;
  logo_url: string | null;
  favicon_url: string | null;
  font_family?: string;
  radius?: string;
  light?: Record<string, string>;
  dark?: Record<string, string>;
}

export interface AppManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  /** Pad van de gebruikersinterface van de app (wordt in een venster geladen). */
  ui?: string | null;
}

export interface AppStatus {
  id: string;
  status: "ok" | "unreachable" | "invalid";
  manifest: AppManifest | null;
  error: string | null;
}

export interface Tenant {
  slug: string;
  name: string;
}

export type TaskbarPosition = "bottom" | "top" | "left" | "right";

export interface Preferences {
  taskbar_position: TaskbarPosition;
  taskbar_autohide: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  preferences?: Preferences;
}

export interface AuditEntry {
  id: number;
  occurred_at: string;
  actor_type: "user" | "assistant" | "system";
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  outcome: "success" | "denied" | "failure";
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  ip: string | null;
  user_agent: string | null;
  request_id: string | null;
}

export interface AuditPage {
  items: AuditEntry[];
  next_before_id: number | null;
}

export interface Session {
  access_token: string;
  expires_in: number;
  user: User;
  tenant: Tenant;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const CORE = "/api/core";
let accessToken: string | null = null;
let refreshing: Promise<Session | null> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Fout ${response.status}`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = "Controleer de ingevulde gegevens";
  } catch {
    /* geen JSON */
  }
  return new ApiError(response.status, message);
}

async function send(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  return sendTo(CORE, path, init, retry);
}

async function sendTo(
  base: string,
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${base}${path}`, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && retry && accessToken) {
    const session = await refreshSession();
    if (session) return sendTo(base, path, init, false);
  }
  return response;
}

async function json<T>(path: string, init: RequestInit = {}, base = CORE): Promise<T> {
  const response = await sendTo(base, path, init);
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Vernieuw de sessie met de refresh-cookie (één tegelijk). */
export function refreshSession(): Promise<Session | null> {
  refreshing ??= (async () => {
    try {
      const response = await fetch(`${CORE}/auth/refresh`, {
        method: "POST",
        headers: { "X-Hub-Request": "1", Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        accessToken = null;
        return null;
      }
      const session = (await response.json()) as Session;
      accessToken = session.access_token;
      return session;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

const body = (data: unknown) => JSON.stringify(data);

export const api = {
  publicTenant: () => json<Tenant>("/tenant/public"),
  theme: (tenant?: string) =>
    json<Theme>(tenant ? `/theme?tenant=${encodeURIComponent(tenant)}` : "/theme"),
  apps: () => json<AppStatus[]>("/apps"),

  async login(email: string, password: string): Promise<Session> {
    const session = await json<Session>("/auth/login", {
      method: "POST",
      body: body({ email, password }),
    });
    accessToken = session.access_token;
    return session;
  },
  async logout(): Promise<void> {
    try {
      await fetch(`${CORE}/auth/logout`, {
        method: "POST",
        headers: { "X-Hub-Request": "1" },
        credentials: "same-origin",
      });
    } finally {
      accessToken = null;
    }
  },

  savePreferences: (prefs: Preferences) =>
    json<Preferences>("/me/preferences", { method: "PUT", body: body(prefs) }),
  accessToken: () => accessToken,

  users: () => json<User[]>("/users"),
  createUser: (data: { email: string; display_name: string; password: string; role: Role }) =>
    json<User>("/users", { method: "POST", body: body(data) }),
  updateUser: (id: string, data: Partial<Pick<User, "display_name" | "role" | "is_active">>) =>
    json<User>(`/users/${id}`, { method: "PATCH", body: body(data) }),
  deleteUser: (id: string) => json<void>(`/users/${id}`, { method: "DELETE" }),

  audit: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return json<AuditPage>(`/audit?${query}`);
  },
  verifyAudit: () => json<{ valid: boolean; checked: number; first_invalid_id: number | null }>("/audit/verify"),
  async exportAudit(): Promise<Blob> {
    const response = await send("/audit/export.csv");
    if (!response.ok) throw await parseError(response);
    return response.blob();
  },

  saveTheme: (theme: Theme) => json<Theme>("/theme", { method: "PUT", body: body(theme) }),
  resetTheme: () => json<void>("/theme", { method: "DELETE" }),
};

// ---- Assistent ---------------------------------------------------------------------

const ASSISTANT = "/api/assistant";

export interface AssistantAction {
  id: string;
  app: string;
  tool: string;
  title: string;
  input: Record<string, unknown>;
  status: "executed" | "failed" | "declined" | "needs_confirmation" | "rejected";
}

export interface AssistantTurn {
  conversation_id: string;
  reply: string;
  actions: AssistantAction[];
  pending: AssistantAction[];
}

export const assistant = {
  status: () => json<{ enabled: boolean; model: string | null }>("/status", {}, ASSISTANT),
  chat: (message: string, conversationId?: string) =>
    json<AssistantTurn>(
      "/chat",
      { method: "POST", body: body({ message, conversation_id: conversationId }) },
      ASSISTANT,
    ),
  decide: (conversationId: string, decisions: Record<string, boolean>) =>
    json<AssistantTurn>(
      `/chat/${conversationId}/decisions`,
      { method: "POST", body: body({ decisions }) },
      ASSISTANT,
    ),
};
