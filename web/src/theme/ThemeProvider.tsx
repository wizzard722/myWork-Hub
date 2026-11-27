import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Theme } from "../api";

const fallback: Theme = { name: "myWork-Hub", logo_url: null, favicon_url: null };
const ThemeContext = createContext<Theme>(fallback);

/** Haalt naam, logo en favicon van het thema op bij de core.
 *  Kleuren, lettertype en afronding komen als CSS-variabelen uit theme.css. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(fallback);

  useEffect(() => {
    api.theme().then(setTheme).catch(() => setTheme(fallback));
  }, []);

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

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
