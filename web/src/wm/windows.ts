/** Toestand van alle vensters (reducer, zonder React-afhankelijkheden). */
import { cascade, clampRect, zoneRect, type Rect, type SnapZone } from "./geometry";

export interface WindowState {
  id: string;
  /** Wat er in het venster staat, bijv. "start", "beheer:gebruikers", "app:hello". */
  kind: string;
  title: string;
  rect: Rect;
  z: number;
  minimized: boolean;
  /** Snap-zone of "maximize"; null = vrij zwevend. */
  snapped: SnapZone | null;
  /** Positie vóór snappen/maximaliseren, om terug te zetten. */
  restore: Rect | null;
}

export interface WmState {
  windows: WindowState[];
  nextZ: number;
  counter: number;
}

export type WmAction =
  | { type: "open"; kind: string; title: string; desk: Rect; single?: boolean }
  | { type: "close"; id: string }
  | { type: "focus"; id: string }
  | { type: "minimize"; id: string }
  | { type: "toggleMinimize"; id: string }
  | { type: "move"; id: string; rect: Rect; desk: Rect }
  | { type: "snap"; id: string; zone: SnapZone; desk: Rect }
  | { type: "unsnap"; id: string; desk: Rect; grabX?: number }
  | { type: "toggleMaximize"; id: string; desk: Rect }
  | { type: "relayout"; desk: Rect };

export const initialWm: WmState = { windows: [], nextZ: 1, counter: 0 };

function topmost(windows: WindowState[]): WindowState | undefined {
  return windows.filter((w) => !w.minimized).sort((a, b) => b.z - a.z)[0];
}

export function activeWindow(state: WmState): WindowState | undefined {
  return topmost(state.windows);
}

function update(state: WmState, id: string, fn: (w: WindowState) => WindowState): WmState {
  return { ...state, windows: state.windows.map((w) => (w.id === id ? fn(w) : w)) };
}

export function wmReducer(state: WmState, action: WmAction): WmState {
  switch (action.type) {
    case "open": {
      // Eén venster per onderdeel (bijv. Beheer): bestaand venster naar voren halen.
      const existing = action.single ? state.windows.find((w) => w.kind === action.kind) : undefined;
      if (existing) return wmReducer(state, { type: "focus", id: existing.id });
      const id = `w${state.counter + 1}`;
      const win: WindowState = {
        id,
        kind: action.kind,
        title: action.title,
        rect: cascade(state.windows.length, action.desk),
        z: state.nextZ,
        minimized: false,
        snapped: null,
        restore: null,
      };
      return { windows: [...state.windows, win], nextZ: state.nextZ + 1, counter: state.counter + 1 };
    }
    case "close":
      return { ...state, windows: state.windows.filter((w) => w.id !== action.id) };
    case "focus":
      return {
        ...update(state, action.id, (w) => ({ ...w, z: state.nextZ, minimized: false })),
        nextZ: state.nextZ + 1,
      };
    case "minimize":
      return update(state, action.id, (w) => ({ ...w, minimized: true }));
    case "toggleMinimize": {
      const win = state.windows.find((w) => w.id === action.id);
      if (!win) return state;
      // Zoals Windows: actief venster minimaliseren, anders naar voren halen.
      const isActive = topmost(state.windows)?.id === win.id;
      return isActive ? wmReducer(state, { type: "minimize", id: win.id }) : wmReducer(state, { type: "focus", id: win.id });
    }
    case "move":
      return update(state, action.id, (w) => ({ ...w, rect: clampRect(action.rect, action.desk), snapped: null }));
    case "snap":
      return update(state, action.id, (w) => ({
        ...w,
        restore: w.snapped ? w.restore : w.rect,
        rect: zoneRect(action.zone, action.desk),
        snapped: action.zone,
        minimized: false,
      }));
    case "unsnap":
      return update(state, action.id, (w) => {
        if (!w.snapped || !w.restore) return w;
        // Bij losslepen: originele grootte, onder de muis gecentreerd.
        const x = action.grabX !== undefined ? action.grabX - w.restore.w / 2 : w.restore.x;
        return { ...w, rect: clampRect({ ...w.restore, x, y: w.rect.y }, action.desk), snapped: null, restore: null };
      });
    case "toggleMaximize":
      return update(state, action.id, (w) =>
        w.snapped === "maximize" && w.restore
          ? { ...w, rect: w.restore, snapped: null, restore: null }
          : { ...w, restore: w.snapped ? w.restore : w.rect, rect: zoneRect("maximize", action.desk), snapped: "maximize" },
      );
    case "relayout":
      // Schermgrootte of startbalk gewijzigd: gesnapte vensters opnieuw indelen.
      return {
        ...state,
        windows: state.windows.map((w) =>
          w.snapped ? { ...w, rect: zoneRect(w.snapped, action.desk) } : { ...w, rect: clampRect(w.rect, action.desk) },
        ),
      };
  }
}

/** Indelingen zoals Windows Snap: welke zones samen het scherm vullen. */
export const SNAP_LAYOUTS: { name: string; zones: SnapZone[] }[] = [
  { name: "Twee naast elkaar", zones: ["left", "right"] },
  { name: "Boven en onder", zones: ["top", "bottom"] },
  { name: "Vier kwarten", zones: ["top-left", "top-right", "bottom-left", "bottom-right"] },
  { name: "Links groot, rechts twee", zones: ["left", "top-right", "bottom-right"] },
  { name: "Rechts groot, links twee", zones: ["right", "top-left", "bottom-left"] },
  { name: "Volledig scherm", zones: ["maximize"] },
];
