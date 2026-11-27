export interface Theme {
  name: string;
  logo_url: string | null;
  favicon_url: string | null;
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

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const api = {
  theme: () => getJson<Theme>("/api/core/theme"),
  apps: () => getJson<AppStatus[]>("/api/core/apps"),
};
