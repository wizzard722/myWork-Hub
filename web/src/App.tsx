import { useEffect, useState } from "react";
import { api, type AppStatus } from "./api";
import { useTheme } from "./theme/ThemeProvider";

const statusLabel: Record<AppStatus["status"], string> = {
  ok: "Beschikbaar",
  unreachable: "Niet bereikbaar",
  invalid: "Ongeldig manifest",
};

export function App() {
  const theme = useTheme();
  const [apps, setApps] = useState<AppStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.apps().then(setApps).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        {theme.logo_url ? (
          <img className="logo" src={theme.logo_url} alt={theme.name} />
        ) : (
          <span className="brand">{theme.name}</span>
        )}
      </header>
      <main className="content">
        <h1>Apps</h1>
        {error && <p className="notice danger">Kan de core niet bereiken: {error}</p>}
        {!apps && !error && <p className="muted">Laden…</p>}
        {apps?.length === 0 && <p className="muted">Er zijn nog geen apps aangesloten.</p>}
        <ul className="app-grid">
          {apps?.map((app) => (
            <li key={app.id} className="card">
              <div className="card-head">
                <strong>{app.manifest?.name ?? app.id}</strong>
                <span className={`badge ${app.status}`}>{statusLabel[app.status]}</span>
              </div>
              <p className="muted">{app.manifest?.description ?? app.error}</p>
              {app.manifest && <small className="muted">v{app.manifest.version}</small>}
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
