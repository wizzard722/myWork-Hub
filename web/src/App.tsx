import { useEffect, useState } from "react";
import { api, type AppStatus, type Session } from "./api";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { AssistantPanel } from "./components/AssistantPanel";
import { AuditPage } from "./pages/AuditPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { ThemePage } from "./pages/ThemePage";
import { UsersPage } from "./pages/UsersPage";
import { ThemeProvider } from "./theme/ThemeProvider";
import { AppWindow } from "./wm/AppWindow";
import { Desktop, type WindowKind } from "./wm/Desktop";

const ITEMS: WindowKind[] = [
  { kind: "beheer:gebruikers", title: "Gebruikers", icon: "users", single: true },
  { kind: "beheer:thema", title: "Thema", icon: "palette", single: true },
  { kind: "beheer:audit", title: "Auditlog", icon: "log", single: true },
  { kind: "assistant", title: "Assistent", icon: "sparkle", single: true },
];

const DEEP_LINKS: Record<string, string> = {
  "/beheer/gebruikers": "beheer:gebruikers",
  "/beheer/thema": "beheer:thema",
  "/beheer/audit": "beheer:audit",
};

function Hub({ session }: { session: Session }) {
  const [apps, setApps] = useState<AppStatus[] | null>(null);
  const [appsError, setAppsError] = useState<string | null>(null);
  const isAdmin = session.user.role !== "member";

  useEffect(() => {
    api
      .apps()
      .then(setApps)
      .catch((e: Error) => setAppsError(e.message));
  }, []);

  const items = ITEMS.filter((i) => isAdmin || !i.kind.startsWith("beheer:"));
  const deepLink = DEEP_LINKS[window.location.hash.replace(/^#/, "")];
  const initial = items.find((i) => i.kind === deepLink);

  function render(kind: string) {
    if (kind === "beheer:gebruikers" && isAdmin) return <UsersPage session={session} />;
    if (kind === "beheer:thema" && isAdmin) return <ThemePage />;
    if (kind === "beheer:audit" && isAdmin) return <AuditPage />;
    if (kind === "assistant") return <AssistantPanel />;
    if (kind.startsWith("app:")) return <AppWindow app={apps?.find((a) => `app:${a.id}` === kind)} />;
    return <p className="muted pad">Onbekend onderdeel.</p>;
  }

  return (
    <Desktop
      session={session}
      apps={apps ?? []}
      items={items}
      render={render}
      initial={initial}
      background={<HomePage session={session} apps={apps} appsError={appsError} />}
    />
  );
}

function Root() {
  const { state } = useAuth();
  const tenant = state.status === "authenticated" ? state.session.tenant.slug : undefined;
  return (
    <ThemeProvider tenant={tenant}>
      {state.status === "loading" && <p className="loading muted">Laden…</p>}
      {state.status === "anonymous" && <LoginPage />}
      {state.status === "authenticated" && <Hub session={state.session} />}
    </ThemeProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  );
}
