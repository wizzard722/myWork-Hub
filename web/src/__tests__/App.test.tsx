import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ThemeProvider } from "../theme/ThemeProvider";

const theme = { name: "Klant BV", logo_url: null, favicon_url: null };
const apps = [
  {
    id: "hello",
    status: "ok",
    manifest: { id: "hello", name: "Hello", version: "0.1.0", description: "Voorbeeld" },
    error: null,
  },
  { id: "files", status: "unreachable", manifest: null, error: "ConnectError" },
];

function mockFetch(routes: Record<string, unknown>, failing: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (failing.includes(url)) return new Response("", { status: 502 });
      return new Response(JSON.stringify(routes[url]), { status: 200 });
    }),
  );
}

function renderShell() {
  return render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("web-schil", () => {
  it("toont naam uit het core-thema", async () => {
    mockFetch({ "/api/core/theme": theme, "/api/core/apps": [] });
    renderShell();
    expect(await screen.findByText("Klant BV")).toBeTruthy();
    expect(document.title).toBe("Klant BV");
  });

  it("toont apps met hun status", async () => {
    mockFetch({ "/api/core/theme": theme, "/api/core/apps": apps });
    renderShell();
    expect(await screen.findByText("Hello")).toBeTruthy();
    expect(screen.getByText("Beschikbaar")).toBeTruthy();
    expect(screen.getByText("Niet bereikbaar")).toBeTruthy();
  });

  it("meldt het als de core niet bereikbaar is", async () => {
    mockFetch({ "/api/core/theme": theme }, ["/api/core/apps"]);
    renderShell();
    expect(await screen.findByText(/Kan de core niet bereiken/)).toBeTruthy();
  });

  it("valt terug op standaardnaam als het thema niet laadt", async () => {
    mockFetch({ "/api/core/apps": [] }, ["/api/core/theme"]);
    renderShell();
    expect(await screen.findByText("Er zijn nog geen apps aangesloten.")).toBeTruthy();
    expect(screen.getByText("myWork-Hub")).toBeTruthy();
  });
});
