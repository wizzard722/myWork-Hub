import { describe, expect, it } from "vitest";
import { clampRect, desktopRect, nearEdge, zoneAt, zoneRect, type Rect } from "../wm/geometry";
import { activeWindow, initialWm, wmReducer, type WmState } from "../wm/windows";

const desk: Rect = { x: 0, y: 0, w: 1600, h: 1000 };

describe("snap-zones", () => {
  it("vier kwarten vullen samen het scherm", () => {
    const quarters = (["top-left", "top-right", "bottom-left", "bottom-right"] as const).map((z) =>
      zoneRect(z, desk),
    );
    const area = quarters.reduce((sum, r) => sum + r.w * r.h, 0);
    expect(area).toBe(desk.w * desk.h);
    expect(quarters[3]).toEqual({ x: 800, y: 500, w: 800, h: 500 });
  });

  it("herkent randen en hoeken tijdens slepen", () => {
    expect(zoneAt(5, 500, desk)).toBe("left");
    expect(zoneAt(1595, 500, desk)).toBe("right");
    expect(zoneAt(800, 3, desk)).toBe("maximize");
    expect(zoneAt(3, 20, desk)).toBe("top-left");
    expect(zoneAt(1597, 990, desk)).toBe("bottom-right");
    expect(zoneAt(40, 998, desk)).toBe("bottom-left");
    expect(zoneAt(800, 500, desk)).toBeNull();
  });

  it("houdt de titelbalk bereikbaar en respecteert minimale grootte", () => {
    const r = clampRect({ x: 5000, y: -300, w: 10, h: 10 }, desk);
    expect(r.x).toBeLessThanOrEqual(desk.w - 120);
    expect(r.y).toBe(0);
    expect(r.w).toBe(320);
    expect(r.h).toBe(200);
  });
});

describe("startbalk", () => {
  it("bureaublad houdt rekening met een vaste startbalk", () => {
    expect(desktopRect({ w: 1600, h: 1000 }, "bottom", false)).toEqual({ x: 0, y: 0, w: 1600, h: 944 });
    expect(desktopRect({ w: 1600, h: 1000 }, "left", false)).toEqual({ x: 56, y: 0, w: 1544, h: 1000 });
    expect(desktopRect({ w: 1600, h: 1000 }, "right", true)).toEqual({ x: 0, y: 0, w: 1600, h: 1000 });
  });

  it("komt tevoorschijn als de muis bij de rand komt, aan elke zijde", () => {
    const vp = { w: 1600, h: 1000 };
    expect(nearEdge(800, 990, vp, "bottom")).toBe(true);
    expect(nearEdge(800, 500, vp, "bottom")).toBe(false);
    expect(nearEdge(800, 10, vp, "top")).toBe(true);
    expect(nearEdge(10, 500, vp, "left")).toBe(true);
    expect(nearEdge(1590, 500, vp, "right")).toBe(true);
    expect(nearEdge(1590, 500, vp, "left")).toBe(false);
  });
});

describe("vensters", () => {
  function open(state: WmState, kind: string, single = false) {
    return wmReducer(state, { type: "open", kind, title: kind, desk, single });
  }

  it("opent meerdere vensters naast elkaar, nieuwste bovenop", () => {
    let s = open(initialWm, "app:hello");
    s = open(s, "app:hello");
    expect(s.windows).toHaveLength(2);
    expect(activeWindow(s)?.id).toBe("w2");
    expect(s.windows[1]!.rect.x).toBeGreaterThan(s.windows[0]!.rect.x);
  });

  it("enkelvoudige vensters worden hergebruikt", () => {
    let s = open(initialWm, "beheer:gebruikers", true);
    s = open(s, "start");
    s = open(s, "beheer:gebruikers", true);
    expect(s.windows).toHaveLength(2);
    expect(activeWindow(s)?.kind).toBe("beheer:gebruikers");
  });

  it("snap en terugzetten", () => {
    let s = open(initialWm, "a");
    const original = s.windows[0]!.rect;
    s = wmReducer(s, { type: "snap", id: "w1", zone: "top-right", desk });
    expect(s.windows[0]!.rect).toEqual({ x: 800, y: 0, w: 800, h: 500 });
    s = wmReducer(s, { type: "snap", id: "w1", zone: "left", desk });
    s = wmReducer(s, { type: "unsnap", id: "w1", desk });
    expect(s.windows[0]!.rect.w).toBe(original.w);
    expect(s.windows[0]!.snapped).toBeNull();
  });

  it("maximaliseren wisselt heen en weer", () => {
    let s = open(initialWm, "a");
    const original = s.windows[0]!.rect;
    s = wmReducer(s, { type: "toggleMaximize", id: "w1", desk });
    expect(s.windows[0]!.rect).toEqual(desk);
    s = wmReducer(s, { type: "toggleMaximize", id: "w1", desk });
    expect(s.windows[0]!.rect).toEqual(original);
  });

  it("klik op taakbalkknop: actief venster minimaliseert, ander komt naar voren", () => {
    let s = open(open(initialWm, "a"), "b");
    s = wmReducer(s, { type: "toggleMinimize", id: "w2" });
    expect(s.windows[1]!.minimized).toBe(true);
    expect(activeWindow(s)?.id).toBe("w1");
    s = wmReducer(s, { type: "toggleMinimize", id: "w2" });
    expect(s.windows[1]!.minimized).toBe(false);
    expect(activeWindow(s)?.id).toBe("w2");
  });

  it("gesnapte vensters volgen een nieuwe schermgrootte", () => {
    let s = open(initialWm, "a");
    s = wmReducer(s, { type: "snap", id: "w1", zone: "right", desk });
    s = wmReducer(s, { type: "relayout", desk: { x: 0, y: 0, w: 1000, h: 800 } });
    expect(s.windows[0]!.rect).toEqual({ x: 500, y: 0, w: 500, h: 800 });
  });
});
