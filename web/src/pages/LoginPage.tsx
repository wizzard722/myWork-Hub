import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type Tenant } from "../api";
import { useAuth } from "../auth/AuthProvider";
import { useTheme } from "../theme/ThemeProvider";

export function LoginPage() {
  const { login } = useAuth();
  const theme = useTheme();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Op een subdomein: laat zien bij welke klant je inlogt.
    api.publicTenant().then(setTenant).catch(() => setTenant(null));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Inloggen mislukt, probeer het opnieuw");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <img
          className="login-logo"
          src={theme.logo_url ?? "/logo-mark.svg"}
          alt=""
          width={56}
          height={56}
        />
        <h1 id="login-title">Inloggen</h1>
        <p className="muted">{tenant ? tenant.name : theme.name}</p>
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        <label className="field">
          <span>E-mailadres</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Wachtwoord</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? "Bezig…" : "Inloggen"}
        </button>
      </form>
    </main>
  );
}
