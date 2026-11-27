import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Theme } from "../api";

const fallback: Theme = { name: "myWork-Hub", logo_url: null, favicon_url: "/favicon.svg" };

interface ThemeContextValue {
  theme: Theme;
  /** Opnieuw laden, bijv. na inloggen (klant bekend) of na opslaan van het thema. */
  reload: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({ theme: fallback, reload: () => {} });

/** Haalt het thema van de klant op bij de core.
 *  Zonder subdomein wordt na inloggen de klant meegegeven via ?tenant=. */
export function ThemeProvider({ tenant, children }: { tenant?: string; children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(fallback);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api
      .theme(tenant)
      .then(setTheme)
      .catch(() => setTheme(fallback));
    const link = document.querySelector<HTMLLinkElement>("link[data-theme-css]");
    if (link) {
      const query = new URLSearchParams();
      if (tenant) query.set("tenant", tenant);
      if (version) query.set("v", String(version));
      const qs = query.toString();
      link.href = `/api/core/theme/theme.css${qs ? `?${qs}` : ""}`;
    }
  }, [tenant, version]);

  useEffect(() => {
    document.title = theme.name;
    if (theme.favicon_url) {
      let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
      if (!link) {
        link = document.createElement("link");
        link.rel = "icon";
        document.head.appendChild(link);
      }
      link.href = theme.favicon_url;
    }
  }, [theme]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return <ThemeContext.Provider value={{ theme, reload }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext).theme;
export const useThemeReload = () => useContext(ThemeContext).reload;
