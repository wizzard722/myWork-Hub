import { useEffect, useState } from "react";
import { api, type AppStatus, type Session } from "./api";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { Shell } from "./components/Shell";
import { useHashRoute } from "./components/useHashRoute";
import { AdminNav } from "./pages/AdminNav";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { ThemePage } from "./pages/ThemePage";
import { UsersPage } from "./pages/UsersPage";
import { ThemeProvider } from "./theme/ThemeProvider";

function Hub({ session }: { session: Session }) {
  const route = useHashRoute();
  const [apps, setApps] = useState<AppStatus[] | null>(null);
  const [appsError, setAppsError] = useState<string | null>(null);
  const isAdmin = session.user.role !== "member";

  useEffect(() => {
    api
      .apps()
      .then(setApps)
      .catch((e: Error) => setAppsError(e.message));
  }, []);

  let page;
  if (route.startsWith("/beheer") && isAdmin) {
    page = (
      <>
        <AdminNav route={route} />
        {route === "/beheer/thema" ? <ThemePage /> : <UsersPage session={session} />}
      </>
    );
  } else if (route.startsWith("/apps/")) {
    const app = apps?.find((a) => `/apps/${a.id}` === route);
    page = (
      <section className="section">
        <h1>{app?.manifest?.name ?? "App"}</h1>
        <p className="muted">
          Het inladen van app-schermen in de hub volgt in fase 5. De API van deze app staat op{" "}
          <a href={`/api/apps/${app?.id ?? ""}/docs`}>/api/apps/{app?.id}/docs</a>.
        </p>
      </section>
    );
  } else {
    page = <HomePage session={session} apps={apps} appsError={appsError} />;
  }

  return (
    <Shell session={session} apps={apps ?? []} route={route}>
      {page}
    </Shell>
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
