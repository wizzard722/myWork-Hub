import { useEffect, useState, type ReactNode } from "react";
import { assistant } from "../api";
import type { AppStatus, Session } from "../api";
import { useAuth } from "../auth/AuthProvider";
import { useTheme } from "../theme/ThemeProvider";
import { AssistantPanel } from "./AssistantPanel";
import { Icon } from "./Icon";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

/** Schil volgens ontwerp-variant B: apps als dock in de gekleurde bovenbalk. */
export function Shell({
  session,
  apps,
  route,
  children,
}: {
  session: Session;
  apps: AppStatus[];
  route: string;
  children: ReactNode;
}) {
  const theme = useTheme();
  const { logout } = useAuth();
  const isAdmin = session.user.role !== "member";
  const available = apps.filter((app) => app.status === "ok" && app.manifest);
  const [assistantEnabled, setAssistantEnabled] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  useEffect(() => {
    assistant
      .status()
      .then((s) => setAssistantEnabled(s.enabled))
      .catch(() => setAssistantEnabled(false));
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#/">
          <img
            className="mark"
            src={theme.logo_url ?? "/logo-mark.svg"}
            alt=""
            width={32}
            height={32}
          />
          <span>{theme.name}</span>
        </a>
        <nav className="dock" aria-label="Apps">
          <a href="#/" className="dock-item" aria-current={route === "/" ? "page" : undefined}>
            <Icon name="home" />
            Start
          </a>
          {available.map((app) => (
            <a
              key={app.id}
              href={`#/apps/${app.id}`}
              className="dock-item"
              aria-current={route === `/apps/${app.id}` ? "page" : undefined}
            >
              <Icon name="grid" />
              {app.manifest!.name}
            </a>
          ))}
          {isAdmin && (
            <a
              href="#/beheer/gebruikers"
              className="dock-item"
              aria-current={route.startsWith("/beheer") ? "page" : undefined}
            >
              <Icon name="gear" />
              Beheer
            </a>
          )}
        </nav>
        <div className="account">
          {assistantEnabled && (
            <button
              type="button"
              className="icon-button"
              onClick={() => setAssistantOpen((o) => !o)}
              aria-label="Assistent"
              aria-expanded={assistantOpen}
              title="Assistent"
            >
              <Icon name="sparkle" />
            </button>
          )}
          <span className="avatar" title={session.user.display_name} aria-hidden="true">
            {initials(session.user.display_name)}
          </span>
          <button
            type="button"
            className="icon-button"
            onClick={() => void logout()}
            aria-label="Uitloggen"
            title="Uitloggen"
          >
            <Icon name="logout" />
          </button>
        </div>
      </header>
      <main className="content">{children}</main>
      {assistantOpen && <AssistantPanel onClose={() => setAssistantOpen(false)} />}
    </div>
  );
}
