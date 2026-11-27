import { useMemo, useState } from "react";
import type { AppStatus, Session } from "../api";
import { Icon } from "../components/Icon";
import { useDesktop } from "../wm/Desktop";

const statusLabel: Record<AppStatus["status"], string> = {
  ok: "Beschikbaar",
  unreachable: "Niet bereikbaar",
  invalid: "Ongeldig manifest",
};

function greeting(date: Date): string {
  const hour = date.getHours();
  if (hour < 6) return "Goedenacht";
  if (hour < 12) return "Goedemorgen";
  if (hour < 18) return "Goedemiddag";
  return "Goedenavond";
}

export function HomePage({
  session,
  apps,
  appsError,
}: {
  session: Session;
  apps: AppStatus[] | null;
  appsError: string | null;
}) {
  const [query, setQuery] = useState("");
  const desktop = useDesktop();
  const firstName = session.user.display_name.split(" ")[0];
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (apps ?? []).filter((app) => {
      const text = `${app.manifest?.name ?? app.id} ${app.manifest?.description ?? ""}`;
      return !q || text.toLowerCase().includes(q);
    });
  }, [apps, query]);

  return (
    <>
      <section className="hero">
        <h1>
          {greeting(new Date())}, {firstName}
        </h1>
        <p className="muted">{session.tenant.name}</p>
        <label className="search">
          <Icon name="search" size={18} />
          <span className="visually-hidden">Zoeken in apps</span>
          <input
            type="search"
            placeholder="Zoek een app…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </section>

      <section className="section">
        <h2>Je apps</h2>
        {appsError && (
          <p className="notice danger" role="alert">
            Kan de apps niet laden: {appsError}
          </p>
        )}
        {!apps && !appsError && <p className="muted">Laden…</p>}
        {apps && visible.length === 0 && (
          <p className="muted">
            {query ? "Geen apps gevonden." : "Er zijn nog geen apps aangesloten."}
          </p>
        )}
        <ul className="tiles">
          {visible.map((app) => (
            <li key={app.id}>
              <button
                type="button"
                className="tile"
                disabled={app.status !== "ok"}
                onClick={() =>
                  desktop.open({ kind: `app:${app.id}`, title: app.manifest?.name ?? app.id, icon: "grid" })
                }
              >
                <span className="tile-icon" aria-hidden="true">
                  {(app.manifest?.name ?? app.id).slice(0, 1).toUpperCase()}
                </span>
                <strong>{app.manifest?.name ?? app.id}</strong>
                <span className="muted small">{app.manifest?.description ?? app.error}</span>
                <span className={`badge ${app.status}`}>{statusLabel[app.status]}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
