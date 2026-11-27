/** Geometrie van de windowmanager: snap-zones en vensterposities (pure functies). */

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type SnapZone =
  | "left"
  | "right"
  | "top"
  | "bottom"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right"
  | "maximize";

export type TaskbarPosition = "bottom" | "top" | "left" | "right";

export const MIN_W = 320;
export const MIN_H = 200;
/** Afstand tot de rand (px) waarbinnen slepen een snap-zone activeert. */
export const SNAP_EDGE = 16;
/** Hoekgebied (px) voor snappen naar een kwart. */
export const SNAP_CORNER = 96;

/** Rechthoek die een zone binnen het bureaublad inneemt. */
export function zoneRect(zone: SnapZone, desk: Rect): Rect {
  const halfW = Math.round(desk.w / 2);
  const halfH = Math.round(desk.h / 2);
  const left = { x: desk.x, w: halfW };
  const right = { x: desk.x + halfW, w: desk.w - halfW };
  const top = { y: desk.y, h: halfH };
  const bottom = { y: desk.y + halfH, h: desk.h - halfH };
  switch (zone) {
    case "maximize":
      return { ...desk };
    case "left":
      return { ...left, y: desk.y, h: desk.h };
    case "right":
      return { ...right, y: desk.y, h: desk.h };
    case "top":
      return { x: desk.x, w: desk.w, ...top };
    case "bottom":
      return { x: desk.x, w: desk.w, ...bottom };
    case "top-left":
      return { ...left, ...top };
    case "top-right":
      return { ...right, ...top };
    case "bottom-left":
      return { ...left, ...bottom };
    case "bottom-right":
      return { ...right, ...bottom };
  }
}

/** Welke snap-zone hoort bij de muispositie tijdens het slepen (of geen). */
export function zoneAt(px: number, py: number, desk: Rect): SnapZone | null {
  const nearLeft = px <= desk.x + SNAP_EDGE;
  const nearRight = px >= desk.x + desk.w - SNAP_EDGE;
  const nearTop = py <= desk.y + SNAP_EDGE;
  const nearBottom = py >= desk.y + desk.h - SNAP_EDGE;
  const inTopBand = py <= desk.y + SNAP_CORNER;
  const inBottomBand = py >= desk.y + desk.h - SNAP_CORNER;
  const inLeftBand = px <= desk.x + SNAP_CORNER;
  const inRightBand = px >= desk.x + desk.w - SNAP_CORNER;

  if ((nearLeft && inTopBand) || (nearTop && inLeftBand)) return "top-left";
  if ((nearRight && inTopBand) || (nearTop && inRightBand)) return "top-right";
  if ((nearLeft && inBottomBand) || (nearBottom && inLeftBand)) return "bottom-left";
  if ((nearRight && inBottomBand) || (nearBottom && inRightBand)) return "bottom-right";
  if (nearLeft) return "left";
  if (nearRight) return "right";
  if (nearTop) return "maximize";
  return null;
}

/** Houd een venster binnen het bureaublad en boven de minimale grootte. */
export function clampRect(r: Rect, desk: Rect): Rect {
  const w = Math.max(MIN_W, Math.min(r.w, desk.w));
  const h = Math.max(MIN_H, Math.min(r.h, desk.h));
  // Titelbalk moet altijd bereikbaar blijven.
  const x = Math.min(Math.max(r.x, desk.x - w + 120), desk.x + desk.w - 120);
  const y = Math.min(Math.max(r.y, desk.y), desk.y + desk.h - 40);
  return { x, y, w, h };
}

/** Beginpositie voor een nieuw venster: trapsgewijs verschoven. */
export function cascade(index: number, desk: Rect): Rect {
  const w = Math.min(900, Math.round(desk.w * 0.6));
  const h = Math.min(640, Math.round(desk.h * 0.7));
  const step = 32 * (index % 8);
  return clampRect({ x: desk.x + 60 + step, y: desk.y + 40 + step, w, h }, desk);
}

/** Bureaubladruimte: het hele scherm, minus de startbalk als die niet automatisch verbergt. */
export function desktopRect(
  viewport: { w: number; h: number },
  position: TaskbarPosition,
  autohide: boolean,
  barSize = 56,
): Rect {
  const full = { x: 0, y: 0, w: viewport.w, h: viewport.h };
  if (autohide) return full;
  switch (position) {
    case "bottom":
      return { ...full, h: full.h - barSize };
    case "top":
      return { ...full, y: barSize, h: full.h - barSize };
    case "left":
      return { ...full, x: barSize, w: full.w - barSize };
    case "right":
      return { ...full, w: full.w - barSize };
  }
}

/** Is de muis dicht genoeg bij de rand van de startbalk om hem te tonen? */
export function nearEdge(
  px: number,
  py: number,
  viewport: { w: number; h: number },
  position: TaskbarPosition,
  distance = 24,
): boolean {
  switch (position) {
    case "bottom":
      return py >= viewport.h - distance;
    case "top":
      return py <= distance;
    case "left":
      return px <= distance;
    case "right":
      return px >= viewport.w - distance;
  }
}
