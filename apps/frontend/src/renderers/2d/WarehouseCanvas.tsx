import { useEffect, useRef, useState } from "react";
import { Minus, Plus, Scan, Move } from "lucide-react";
import { WarehouseRenderer } from "./WarehouseRenderer";
import type { WarehouseViewProps } from "../shared/scene";
import type { Point } from "@/types/domain";
import { usePreferences } from "@/stores/simulation";
export function WarehouseCanvas({
  frame,
  onCell,
  onHover,
  onSelect,
  editing = false,
  paintDrag = false,
}: WarehouseViewProps) {
  const painted = useRef<string | null>(null);
  const hoverKey = useRef<string | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const renderer = useRef<WarehouseRenderer | null>(null);
  const latest = useRef(frame);
  latest.current = frame;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>([0, 0]);
  const drag = useRef<{
    x: number;
    y: number;
    pan: Point;
    moved: boolean;
  } | null>(null);
  const layers = usePreferences((s) => s.layers);
  useEffect(() => {
    const r = new WarehouseRenderer();
    renderer.current = r;
    const el = host.current!;
    void r
      .init(el)
      .then(() => {
        if (!r.destroyed) {
          setReady(true);
          r.update(latest.current, usePreferences.getState().layers);
        }
      })
      .catch((e) => setError(String(e)));
    const observer = new ResizeObserver(() =>
      r.resize(el.clientWidth, el.clientHeight),
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      r.destroy();
    };
  }, []);
  useEffect(() => {
    if (ready) renderer.current?.update(frame, layers);
  }, [frame, layers, ready]);
  useEffect(() => {
    renderer.current?.setCamera(zoom, pan);
  }, [zoom, pan]);
  const cellAt = (x: number, y: number) => {
    const rect = host.current!.getBoundingClientRect();
    return renderer.current?.pick(x - rect.left, y - rect.top) ?? null;
  };
  return (
    <div className="map-surface">
      <div
        ref={host}
        className="map-canvas"
        role="application"
        aria-label="Interaktivní mapa skladu"
        onContextMenu={(e) => e.preventDefault()}
        onWheel={(e) =>
          setZoom((z) =>
            Math.max(0.5, Math.min(4, z * (e.deltaY < 0 ? 1.1 : 0.9))),
          )
        }
        onPointerDown={(e) => {
          if (editing && paintDrag && e.button === 0) {
            const p = cellAt(e.clientX, e.clientY);
            if (p) {
              painted.current = p.join(",");
              onCell?.(p);
            }
            e.currentTarget.setPointerCapture(e.pointerId);
          }
          if (e.button === 1 || e.button === 2 || !editing) {
            drag.current = { x: e.clientX, y: e.clientY, pan, moved: false };
            e.currentTarget.setPointerCapture(e.pointerId);
          }
        }}
        onPointerMove={(e) => {
          if (drag.current) {
            const dx = e.clientX - drag.current.x,
              dy = e.clientY - drag.current.y;
            if (Math.abs(dx) + Math.abs(dy) > 4) drag.current.moved = true;
            if (drag.current.moved)
              setPan([drag.current.pan[0] + dx, drag.current.pan[1] + dy]);
          }
          const p = cellAt(e.clientX, e.clientY);
          if (
            editing &&
            paintDrag &&
            e.buttons === 1 &&
            p &&
            painted.current !== p.join(",")
          ) {
            painted.current = p.join(",");
            onCell?.(p);
          }
          if (hoverKey.current !== (p?.join(",") ?? null)) {
            hoverKey.current = p?.join(",") ?? null;
            onHover?.(p);
          }
        }}
        onPointerLeave={() => {
          hoverKey.current = null;
          onHover?.(null);
        }}
        onPointerUp={(e) => {
          const moved = drag.current?.moved;
          const didPaint = painted.current !== null;
          painted.current = null;
          drag.current = null;
          if (moved || didPaint || e.button !== 0) return;
          const p = cellAt(e.clientX, e.clientY);
          if (!p) return;
          const robot = frame.robots.find(
            (r) => r.position[0] === p[0] && r.position[1] === p[1],
          );
          if (robot && !editing) onSelect?.(robot.id);
          else onCell?.(p);
        }}
      />
      {error && <div className="map-error">Mapu nelze vykreslit: {error}</div>}
      <div className="map-camera">
        <span>
          <Move size={12} /> Tažením posunout · kolečkem přiblížit
        </span>
        <button
          aria-label="Oddálit"
          onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))}
        >
          <Minus size={15} />
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          aria-label="Přiblížit"
          onClick={() => setZoom((z) => Math.min(4, z + 0.2))}
        >
          <Plus size={15} />
        </button>
        <button
          aria-label="Zobrazit celou mapu"
          onClick={() => {
            setZoom(1);
            setPan([0, 0]);
          }}
        >
          <Scan size={15} />
        </button>
      </div>
    </div>
  );
}
