import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { setAccessToken } from "../api";

type Handler = (init: RequestInit) => { status: number; body?: unknown };
type Routes = Record<string, Handler | unknown>;

const tenant = { slug: "acme", name: "Acme BV" };
const owner = {
  id: "u1",
  email: "eigenaar@acme.nl",
  display_name: "Jan de Vries",
  role: "owner",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};
const member = { ...owner, id: "u2", email: "lid@acme.nl", display_name: "Sanne Bakker", role: "member" };
const session = (user = owner) => ({ access_token: "tok", expires_in: 900, user, tenant });
const theme = { name: "Acme Portaal", logo_url: null, favicon_url: "/favicon.svg", light: { primary: "#0b5fff" } };
const apps = [
  {
    id: "hello",
    status: "ok",
    manifest: { id: "hello", name: "Hello", version: "0.1.0", description: "Voorbeeld" },
    error: null,
  },
  { id: "files", status: "unreachable", manifest: null, error: "ConnectError" },
];

let calls: { method: string; url: string; body?: string }[] = [];

function mockApi(routes: Routes) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method ?? "GET").toUpperCase();
      const path = url.replace(/^\/api\/(core|assistant)/, "").split("?")[0];
      calls.push({ method, url, body: init.body as string | undefined });
      const route = routes[`${method} ${path}`];
      if (route === undefined) return new Response(JSON.stringify({ detail: "niet gevonden" }), { status: 404 });
      const result = typeof route === "function" ? (route as Handler)(init) : { status: 200, body: route };
      const status = result.status;
      return new Response(status === 204 ? null : JSON.stringify(result.body ?? {}), { status });
    }),
  );
}

const anonymous = { "POST /auth/refresh": () => ({ status: 401, body: { detail: "Geen sessie" } }) };
const loggedIn = (user = owner) => ({
  "POST /auth/refresh": session(user),
  "GET /theme": theme,
  "GET /apps": apps,
});

beforeEach(() => {
  window.location.hash = "";
  setAccessToken(null);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("inloggen", () => {
  it("toont inlogscherm met klantnaam van het subdomein", async () => {
    mockApi({ ...anonymous, "GET /tenant/public": tenant, "GET /theme": theme });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Inloggen" })).toBeTruthy();
    expect(await screen.findByText("Acme BV")).toBeTruthy();
  });

  it("logt in en toont de hub", async () => {
    mockApi({ ...anonymous, "GET /theme": theme, "POST /auth/login": session(), "GET /apps": apps });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("E-mailadres"), {
      target: { value: "eigenaar@acme.nl" },
    });
    fireEvent.change(screen.getByLabelText("Wachtwoord"), { target: { value: "geheim-wachtwoord" } });
    fireEvent.click(screen.getByRole("button", { name: "Inloggen" }));
    expect(await screen.findByText(/, Jan$/)).toBeTruthy();
    const login = calls.find((c) => c.url.endsWith("/auth/login"))!;
    expect(JSON.parse(login.body!)).toEqual({ email: "eigenaar@acme.nl", password: "geheim-wachtwoord" });
    // Na inloggen het thema van de klant laden.
    await waitFor(() => expect(calls.some((c) => c.url.includes("/theme?tenant=acme"))).toBe(true));
  });

  it("toont foutmelding bij verkeerd wachtwoord", async () => {
    mockApi({
      ...anonymous,
      "GET /theme": theme,
      "POST /auth/login": () => ({ status: 401, body: { detail: "E-mailadres of wachtwoord klopt niet" } }),
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("E-mailadres"), { target: { value: "a@b.nl" } });
    fireEvent.change(screen.getByLabelText("Wachtwoord"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Inloggen" }));
    expect((await screen.findByRole("alert")).textContent).toContain("klopt niet");
  });

  it("hervat een bestaande sessie en logt uit", async () => {
    mockApi({ ...loggedIn(), "POST /auth/logout": () => ({ status: 204 }) });
    render(<App />);
    expect(await screen.findByText(/, Jan$/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Uitloggen" }));
    expect(await screen.findByRole("heading", { name: "Inloggen" })).toBeTruthy();
  });
});

describe("hub (variant B)", () => {
  it("toont apps in dock en tegels, met status", async () => {
    mockApi(loggedIn());
    render(<App />);
    const dock = await screen.findByRole("navigation", { name: "Apps" });
    await waitFor(() => expect(dock.textContent).toContain("Hello"));
    expect(dock.textContent).not.toContain("files"); // niet bereikbaar: niet in dock
    expect(screen.getByText("Niet bereikbaar")).toBeTruthy();
    expect(screen.getByText("Acme Portaal")).toBeTruthy();
  });

  it("zoeken filtert de apps", async () => {
    mockApi(loggedIn());
    render(<App />);
    await screen.findByText("Voorbeeld");
    fireEvent.change(screen.getByPlaceholderText("Zoek een app…"), { target: { value: "xyz" } });
    expect(screen.getByText("Geen apps gevonden.")).toBeTruthy();
  });

  it("beheer alleen zichtbaar voor beheerders", async () => {
    mockApi(loggedIn(member));
    render(<App />);
    const dock = await screen.findByRole("navigation", { name: "Apps" });
    expect(dock.textContent).not.toContain("Beheer");
    window.location.hash = "#/beheer/gebruikers";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(screen.queryByRole("heading", { name: "Gebruikers" })).toBeNull();
  });
});

describe("beheer", () => {
  it("toont gebruikers en voegt er een toe", async () => {
    window.location.hash = "#/beheer/gebruikers";
    mockApi({
      ...loggedIn(),
      "GET /users": [owner, member],
      "POST /users": () => ({ status: 201, body: { ...member, id: "u3", email: "nieuw@acme.nl" } }),
    });
    render(<App />);
    expect(await screen.findByText("lid@acme.nl")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Naam"), { target: { value: "Nieuw" } });
    fireEvent.change(screen.getAllByLabelText("E-mailadres")[0]!, { target: { value: "nieuw@acme.nl" } });
    fireEvent.change(screen.getByLabelText("Wachtwoord (minimaal 12 tekens)"), {
      target: { value: "een-lang-wachtwoord" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Toevoegen" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/users"))).toBe(true));
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/users"))!;
    expect(JSON.parse(post.body!)).toMatchObject({ email: "nieuw@acme.nl", role: "member" });
  });

  it("eigen rol is niet te wijzigen", async () => {
    window.location.hash = "#/beheer/gebruikers";
    mockApi({ ...loggedIn(), "GET /users": [owner, member] });
    render(<App />);
    const own = (await screen.findByLabelText("Rol van Jan de Vries")) as HTMLSelectElement;
    expect(own.disabled).toBe(true);
    expect((screen.getByLabelText("Rol van Sanne Bakker") as HTMLSelectElement).disabled).toBe(false);
  });

  it("slaat het thema op", async () => {
    window.location.hash = "#/beheer/thema";
    mockApi({ ...loggedIn(), "PUT /theme": theme });
    render(<App />);
    const name = (await screen.findByLabelText("Naam van de hub")) as HTMLInputElement;
    await waitFor(() => expect(name.value).toBe("Acme Portaal"));
    fireEvent.change(name, { target: { value: "Nieuwe naam" } });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));
    expect(await screen.findByText("Thema opgeslagen")).toBeTruthy();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(JSON.parse(put.body!).name).toBe("Nieuwe naam");
  });
});

describe("styles", () => {
  it("vangnetwaarden overschrijven het core-thema nooit", async () => {
    const css = (await import("../styles.css?raw")).default;
    // Alleen :where(:root) mag --mw-variabelen definiëren (specificiteit 0).
    const blocks = [...css.matchAll(/([^{}]+)\{[^}]*--mw-color-primary:/g)].map((m) => m[1]!.trim());
    expect(blocks.every((selector) => selector.endsWith(":where(:root)"))).toBe(true);
  });
});

describe("auditlog", () => {
  const entry = {
    id: 7,
    occurred_at: "2026-11-27T14:00:00Z",
    actor_type: "user",
    actor_email: "eigenaar@acme.nl",
    actor_role: "owner",
    action: "user.role_changed",
    outcome: "success",
    target_type: "user",
    target_id: "u2",
    details: { email: "lid@acme.nl", changes: { role: ["member", "admin"] } },
    ip: "203.0.113.7",
    user_agent: "x",
    request_id: "r1",
  };

  it("toont wie wat wanneer deed en controleert de integriteit", async () => {
    window.location.hash = "#/beheer/audit";
    mockApi({
      ...loggedIn(),
      "GET /audit": { items: [entry, { ...entry, id: 6, action: "auth.login_failed", outcome: "denied", details: { reason: "wachtwoord onjuist" } }], next_before_id: null },
      "GET /audit/verify": { valid: true, checked: 7, first_invalid_id: null },
    });
    render(<App />);
    expect(await screen.findByText("Rol gewijzigd")).toBeTruthy();
    expect(screen.getByText(/role: member → admin/)).toBeTruthy();
    expect(screen.getAllByText("203.0.113.7").length).toBe(2);
    expect(screen.getByText("Geweigerd", { selector: ".badge" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Integriteit controleren/ }));
    expect(await screen.findByText(/Integriteit in orde: 7 regels/)).toBeTruthy();
  });

  it("filtert op handeling", async () => {
    window.location.hash = "#/beheer/audit";
    mockApi({ ...loggedIn(), "GET /audit": { items: [], next_before_id: null } });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Handeling"), { target: { value: "user." } });
    await waitFor(() => expect(calls.some((c) => c.url.includes("action=user."))).toBe(true));
  });
});

describe("assistent", () => {
  const turn = (extra: object) => ({ conversation_id: "c".repeat(32), reply: "", actions: [], pending: [], ...extra });

  it("is verborgen als de assistent uit staat", async () => {
    mockApi({ ...loggedIn(), "GET /status": { enabled: false, model: null } });
    render(<App />);
    await screen.findByText("Je apps");
    expect(screen.queryByRole("button", { name: "Assistent" })).toBeNull();
  });

  it("vraagt bevestiging voor wijzigende acties en voert pas daarna uit", async () => {
    // Zoals in nieuwere Chrome-versies: scrollIntoView geeft een Promise terug.
    Element.prototype.scrollIntoView = () => Promise.resolve() as unknown as void;
    const pending = {
      id: "tu1",
      app: "core",
      tool: "change_user_role",
      title: "Wijzig de rol van een gebruiker",
      input: { user_id: "u2", role: "admin" },
      status: "needs_confirmation",
    };
    mockApi({
      ...loggedIn(),
      "GET /status": { enabled: true, model: "claude-opus-5-5" },
      "POST /chat": turn({ reply: "Ik maak Sanne beheerder.", pending: [pending] }),
      "POST /chat/cccccccccccccccccccccccccccccccc/decisions": turn({
        reply: "Sanne is nu beheerder.",
        actions: [{ ...pending, status: "executed" }],
      }),
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Assistent" }));
    fireEvent.change(screen.getByLabelText("Bericht aan de assistent"), {
      target: { value: "Maak Sanne beheerder" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Versturen" }));
    expect(await screen.findByText("Ik maak Sanne beheerder.")).toBeTruthy();
    expect(screen.getByText(/role: admin/)).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/decisions"))).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Uitvoeren" }));
    expect(await screen.findByText("Sanne is nu beheerder.")).toBeTruthy();
    const decide = calls.find((c) => c.url.includes("/decisions"))!;
    expect(JSON.parse(decide.body!)).toEqual({ decisions: { tu1: true } });
    expect(screen.getByText(/change_user_role — Uitgevoerd/)).toBeTruthy();
  });
});
