import { useEffect, useRef, useState, type ReactNode } from "react";
import type { TaskbarPosition } from "./geometry";
import { nearEdge } from "./geometry";

interface Props {
  position: TaskbarPosition;
  autohide: boolean;
  /** Startmenu of ander menu open: balk blijft zichtbaar. */
  pinned: boolean;
  children: ReactNode;
}

const HIDE_DELAY = 700;

/** Startbalk aan een van de vier zijden. Bij automatisch verbergen schuift hij weg en
 *  komt terug zodra de muis de rand nadert, erover beweegt of er toetsenbordfocus in zit. */
export function Taskbar({ position, autohide, pinned, children }: Props) {
  const [revealed, setRevealed] = useState(!autohide);
  const hovering = useRef(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!autohide) {
      setRevealed(true);
      return;
    }
    setRevealed(false);
    function onMove(event: MouseEvent) {
      const viewport = { w: window.innerWidth, h: window.innerHeight };
      if (nearEdge(event.clientX, event.clientY, viewport, position) || hovering.current) {
        window.clearTimeout(timer.current);
        setRevealed(true);
      } else {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setRevealed(false), HIDE_DELAY);
      }
    }
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.clearTimeout(timer.current);
    };
  }, [autohide, position]);

  const shown = !autohide || revealed || pinned;
  const vertical = position === "left" || position === "right";
  return (
    <nav
      className={`taskbar pos-${position}${vertical ? " vertical" : ""}${shown ? " shown" : " hidden"}`}
      aria-label="Startbalk"
      data-position={position}
      onMouseEnter={() => {
        hovering.current = true;
        setRevealed(true);
      }}
      onMouseLeave={() => {
        hovering.current = false;
      }}
      onFocus={() => setRevealed(true)}
    >
      {children}
    </nav>
  );
}
