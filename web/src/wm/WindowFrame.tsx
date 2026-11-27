import { useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { Icon } from "../components/Icon";
import { zoneAt, type Rect, type SnapZone } from "./geometry";
import { SNAP_LAYOUTS, type WindowState, type WmAction } from "./windows";

interface Props {
  win: WindowState;
  desk: Rect;
  active: boolean;
  mobile: boolean;
  dispatch: (action: WmAction) => void;
  onPreview: (zone: SnapZone | null) => void;
  children: ReactNode;
}

type Drag =
  | { mode: "move"; dx: number; dy: number; startX: number; startY: number; moved: boolean }
  | { mode: "resize"; startX: number; startY: number; rect: Rect };

/** Eén venster: verplaatsen, schalen, snappen (slepen naar rand/hoek of indelingsmenu). */
export function WindowFrame({ win, desk, active, mobile, dispatch, onPreview, children }: Props) {
  const drag = useRef<Drag | null>(null);
  const zone = useRef<SnapZone | null>(null);
  const [layoutsOpen, setLayoutsOpen] = useState(false);
  const focus = () => !active && dispatch({ type: "focus", id: win.id });

  function startMove(event: PointerEvent<HTMLDivElement>) {
    if (mobile || event.button !== 0 || (event.target as HTMLElement).closest("button")) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drag.current = {
      mode: "move",
      dx: event.clientX - win.rect.x,
      dy: event.clientY - win.rect.y,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    focus();
  }

  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (mobile) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drag.current = { mode: "resize", startX: event.clientX, startY: event.clientY, rect: win.rect };
    focus();
  }

  function onMove(event: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d) return;
    if (d.mode === "resize") {
      const rect = {
        ...d.rect,
        w: d.rect.w + event.clientX - d.startX,
        h: d.rect.h + event.clientY - d.startY,
      };
      dispatch({ type: "move", id: win.id, rect, desk });
      return;
    }
    if (!d.moved && Math.hypot(event.clientX - d.startX, event.clientY - d.startY) < 5) return;
    if (!d.moved && win.snapped) {
      // Losmaken uit een snap-positie: terug naar de oude grootte onder de muis.
      dispatch({ type: "unsnap", id: win.id, desk, grabX: event.clientX });
      const width = win.restore?.w ?? win.rect.w;
      d.dx = width / 2;
    }
    d.moved = true;
    dispatch({
      type: "move",
      id: win.id,
      rect: { ...win.rect, w: win.restore && win.snapped ? win.restore.w : win.rect.w, h: win.restore && win.snapped ? win.restore.h : win.rect.h, x: event.clientX - d.dx, y: event.clientY - d.dy },
      desk,
    });
    zone.current = zoneAt(event.clientX, event.clientY, desk);
    onPreview(zone.current);
  }

  function endDrag() {
    const d = drag.current;
    drag.current = null;
    if (d?.mode === "move" && d.moved && zone.current) {
      dispatch({ type: "snap", id: win.id, zone: zone.current, desk });
    }
    zone.current = null;
    onPreview(null);
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    // Ctrl+Alt+pijltjes: snappen met het toetsenbord.
    if (!(event.ctrlKey && event.altKey)) return;
    const keys: Record<string, SnapZone | "restore"> = {
      ArrowLeft: "left",
      ArrowRight: "right",
      ArrowUp: "maximize",
      ArrowDown: "restore",
    };
    const target = keys[event.key];
    if (!target) return;
    event.preventDefault();
    if (target === "restore") {
      if (win.snapped) dispatch({ type: "unsnap", id: win.id, desk });
      else dispatch({ type: "minimize", id: win.id });
    } else dispatch({ type: "snap", id: win.id, zone: target, desk });
  }

  if (win.minimized) return null;
  const style = mobile
    ? { zIndex: win.z }
    : { left: win.rect.x, top: win.rect.y, width: win.rect.w, height: win.rect.h, zIndex: win.z };
  const maximized = win.snapped === "maximize";

  return (
    <section
      className={`window${active ? " active" : ""}${win.snapped ? " snapped" : ""}${mobile ? " mobile" : ""}`}
      style={style}
      aria-label={win.title}
      role="dialog"
      onPointerDown={focus}
      onKeyDown={onKeyDown}
    >
      <div
        className="window-titlebar"
        onPointerDown={startMove}
        onPointerMove={onMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => !mobile && dispatch({ type: "toggleMaximize", id: win.id, desk })}
      >
        <span className="window-title">{win.title}</span>
        <div className="window-buttons">
          {!mobile && (
            <div className="layouts">
              <button
                type="button"
                aria-label="Indeling kiezen"
                title="Indeling (snap)"
                aria-expanded={layoutsOpen}
                onClick={() => setLayoutsOpen((o) => !o)}
              >
                <Icon name="layout" size={16} />
              </button>
              {layoutsOpen && (
                <div className="layout-menu" role="menu" aria-label="Indelingen">
                  {SNAP_LAYOUTS.map((layout) => (
                    <div key={layout.name} className={`layout layout-${layout.zones.length}`} title={layout.name}>
                      {layout.zones.map((z) => (
                        <button
                          key={z}
                          type="button"
                          role="menuitem"
                          className={`zone zone-${z}`}
                          aria-label={`${layout.name}: ${ZONE_LABEL[z]}`}
                          onClick={() => {
                            setLayoutsOpen(false);
                            dispatch({ type: "snap", id: win.id, zone: z, desk });
                          }}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <button type="button" aria-label="Minimaliseren" onClick={() => dispatch({ type: "minimize", id: win.id })}>
            <Icon name="minimize" size={16} />
          </button>
          {!mobile && (
            <button
              type="button"
              aria-label={maximized ? "Vorige grootte" : "Maximaliseren"}
              onClick={() => dispatch({ type: "toggleMaximize", id: win.id, desk })}
            >
              <Icon name={maximized ? "restore" : "maximize"} size={16} />
            </button>
          )}
          <button type="button" className="close" aria-label="Sluiten" onClick={() => dispatch({ type: "close", id: win.id })}>
            <Icon name="close" size={16} />
          </button>
        </div>
      </div>
      <div className="window-body">{children}</div>
      {!mobile && !win.snapped && (
        <div
          className="window-resize"
          aria-hidden="true"
          onPointerDown={startResize}
          onPointerMove={onMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        />
      )}
    </section>
  );
}

const ZONE_LABEL: Record<SnapZone, string> = {
  left: "links",
  right: "rechts",
  top: "boven",
  bottom: "onder",
  "top-left": "linksboven",
  "top-right": "rechtsboven",
  "bottom-left": "linksonder",
  "bottom-right": "rechtsonder",
  maximize: "volledig",
};
