import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { api, assistant, type AppStatus, type Preferences, type Session, type TaskbarPosition } from "../api";
import { useAuth } from "../auth/AuthProvider";
import { Icon } from "../components/Icon";
import { useTheme } from "../theme/ThemeProvider";
import { desktopRect, zoneRect, type Rect, type SnapZone } from "./geometry";
import { Taskbar } from "./Taskbar";
import { WindowFrame } from "./WindowFrame";
import { activeWindow, initialWm, wmReducer, type WmState } from "./windows";

export interface WindowKind {
  kind: string;
  title: string;
  icon: "home" | "grid" | "users" | "palette" | "log" | "sparkle";
  /** Maximaal één venster van dit soort. */
  single?: boolean;
}

interface DesktopApi {
  open: (item: WindowKind) => void;
}

const DesktopContext = createContext<DesktopApi>({ open: () => {} });
export const useDesktop = () => useContext(DesktopContext);

const MOBILE_WIDTH = 720;
const DEFAULT_PREFS: Preferences = { taskbar_position: "bottom", taskbar_autohide: true };
const POSITIONS: { value: TaskbarPosition; label: string }[] = [
  { value: "bottom", label: "Onder" },
  { value: "top", label: "Boven" },
  { value: "left", label: "Links" },
  { value: "right", label: "Rechts" },
];

function useViewport() {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return size;
}

function loadLayout(key: string): WmState {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as WmState) : initialWm;
  } catch {
    return initialWm;
  }
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

interface Props {
  session: Session;
  apps: AppStatus[];
  /** Vaste onderdelen die als venster kunnen openen (Beheer, Assistent, ...). */
  items: WindowKind[];
  /** Inhoud van een venster. */
  render: (kind: string) => ReactNode;
  /** Achtergrond van het bureaublad (de startpagina). */
  background: ReactNode;
  /** Venster dat bij het openen al open moet staan (deep link). */
  initial?: WindowKind;
}

/** Bureaublad met vensters, snap-indelingen en een verplaatsbare startbalk. */
export function Desktop({ session, apps, items, render, background, initial }: Props) {
  const theme = useTheme();
  const { logout } = useAuth();
  const viewport = useViewport();
  const mobile = viewport.w < MOBILE_WIDTH;
  const storageKey = `mywork:wm:${session.user.id}`;
  const [state, dispatch] = useReducer(wmReducer, storageKey, loadLayout);
  const [prefs, setPrefs] = useState<Preferences>(session.user.preferences ?? DEFAULT_PREFS);
  const [menu, setMenu] = useState<"start" | "account" | null>(null);
  const [preview, setPreview] = useState<SnapZone | null>(null);
  const [assistantEnabled, setAssistantEnabled] = useState(false);
  const [query, setQuery] = useState("");
  const now = useClock();

  const position = mobile ? "bottom" : prefs.taskbar_position;
  const autohide = mobile ? false : prefs.taskbar_autohide;
  const desk: Rect = useMemo(() => desktopRect(viewport, position, autohide), [viewport, position, autohide]);

  useEffect(() => dispatch({ type: "relayout", desk }), [desk]);
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state));
    } catch {
      /* opslag niet beschikbaar: indeling niet onthouden */
    }
  }, [state, storageKey]);
  useEffect(() => {
    assistant
      .status()
      .then((s) => setAssistantEnabled(s.enabled))
      .catch(() => setAssistantEnabled(false));
  }, []);

  const open = useCallback(
    (item: WindowKind) => {
      setMenu(null);
      dispatch({ type: "open", kind: item.kind, title: item.title, desk, single: item.single });
    },
    [desk],
  );
  const openedInitial = useRef(false);
  useEffect(() => {
    if (initial && !openedInitial.current) {
      openedInitial.current = true;
      open(initial);
    }
  }, [initial, open]);

  async function savePrefs(next: Preferences) {
    setPrefs(next);
    try {
      await api.savePreferences(next);
    } catch {
      /* offline of fout: lokaal blijft het gelden */
    }
  }

  const appItems: WindowKind[] = apps
    .filter((a) => a.status === "ok" && a.manifest)
    .map((a) => ({ kind: `app:${a.id}`, title: a.manifest!.name, icon: "grid" }));
  const allItems = [...appItems, ...items.filter((i) => i.kind !== "assistant" || assistantEnabled)];
  const filtered = allItems.filter((i) => i.title.toLowerCase().includes(query.trim().toLowerCase()));
  const active = activeWindow(state);

  return (
    <DesktopContext.Provider value={{ open }}>
      <div className={`desktop bar-${position}${autohide ? " autohide" : ""}`}>
        <div className="desktop-background" style={{ left: desk.x, top: desk.y, width: desk.w, height: desk.h }}>
          {background}
        </div>

        {preview && (
          <div className="snap-preview" style={(({ x, y, w, h }) => ({ left: x, top: y, width: w, height: h }))(zoneRect(preview, desk))} />
        )}

        {state.windows.map((win) => (
          <WindowFrame
            key={win.id}
            win={win}
            desk={desk}
            active={active?.id === win.id}
            mobile={mobile}
            dispatch={dispatch}
            onPreview={setPreview}
          >
            {render(win.kind)}
          </WindowFrame>
        ))}

        <Taskbar position={position} autohide={autohide} pinned={menu !== null}>
          <button
            type="button"
            className="start-button"
            aria-label="Start"
            aria-expanded={menu === "start"}
            onClick={() => setMenu(menu === "start" ? null : "start")}
          >
            <img src={theme.logo_url ?? "/logo-mark.svg"} alt="" width={28} height={28} />
          </button>

          <div className="task-list" role="list" aria-label="Geopende vensters">
            {state.windows.map((win) => (
              <button
                key={win.id}
                type="button"
                role="listitem"
                className={`task${active?.id === win.id ? " active" : ""}${win.minimized ? " minimized" : ""}`}
                onClick={() => dispatch({ type: "toggleMinimize", id: win.id })}
                title={win.title}
              >
                {win.title}
              </button>
            ))}
          </div>

          <div className="tray">
            {assistantEnabled && (
              <button
                type="button"
                className="icon-button"
                aria-label="Assistent"
                onClick={() => open({ kind: "assistant", title: "Assistent", icon: "sparkle", single: true })}
              >
                <Icon name="sparkle" />
              </button>
            )}
            <time className="clock" dateTime={now.toISOString()}>
              {now.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}
            </time>
            <button
              type="button"
              className="icon-button"
              aria-label="Account"
              aria-expanded={menu === "account"}
              onClick={() => setMenu(menu === "account" ? null : "account")}
            >
              <Icon name="user" />
            </button>
          </div>
        </Taskbar>

        {menu === "start" && (
          <div className={`menu start-menu at-${position}`} role="dialog" aria-label="Startmenu">
            <strong className="menu-title">{theme.name}</strong>
            <label className="search small-search">
              <Icon name="search" size={16} />
              <span className="visually-hidden">Zoeken</span>
              <input autoFocus placeholder="Zoek een app of onderdeel…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <ul className="menu-grid">
              {filtered.map((item) => (
                <li key={item.kind}>
                  <button type="button" onClick={() => open(item)}>
                    <Icon name={item.icon} />
                    <span>{item.title}</span>
                  </button>
                </li>
              ))}
            </ul>
            {filtered.length === 0 && <p className="muted small">Niets gevonden.</p>}
          </div>
        )}

        {menu === "account" && (
          <div className={`menu account-menu at-${position}`} role="dialog" aria-label="Accountmenu">
            <p>
              <strong>{session.user.display_name}</strong>
              <br />
              <span className="muted small">
                {session.user.email} · {session.tenant.name}
              </span>
            </p>
            {!mobile && (
              <fieldset>
                <legend>Startbalk</legend>
                <div className="row">
                  {POSITIONS.map((p) => (
                    <button
                      key={p.value}
                      type="button"
                      className={`button small${prefs.taskbar_position === p.value ? " primary" : ""}`}
                      aria-pressed={prefs.taskbar_position === p.value}
                      onClick={() => void savePrefs({ ...prefs, taskbar_position: p.value })}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={prefs.taskbar_autohide}
                    onChange={(e) => void savePrefs({ ...prefs, taskbar_autohide: e.target.checked })}
                  />
                  Automatisch verbergen
                </label>
              </fieldset>
            )}
            <button type="button" className="button" onClick={() => void logout()}>
              <Icon name="logout" size={16} /> Uitloggen
            </button>
          </div>
        )}
        {menu && <div className="menu-backdrop" onClick={() => setMenu(null)} aria-hidden="true" />}
      </div>
    </DesktopContext.Provider>
  );
}
