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

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
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
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${CORE}${path}`, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && retry && accessToken) {
    const session = await refreshSession();
    if (session) return send(path, init, false);
  }
  return response;
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init);
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

  users: () => json<User[]>("/users"),
  createUser: (data: { email: string; display_name: string; password: string; role: Role }) =>
    json<User>("/users", { method: "POST", body: body(data) }),
  updateUser: (id: string, data: Partial<Pick<User, "display_name" | "role" | "is_active">>) =>
    json<User>(`/users/${id}`, { method: "PATCH", body: body(data) }),
  deleteUser: (id: string) => json<void>(`/users/${id}`, { method: "DELETE" }),

  saveTheme: (theme: Theme) => json<Theme>("/theme", { method: "PUT", body: body(theme) }),
  resetTheme: () => json<void>("/theme", { method: "DELETE" }),
};
