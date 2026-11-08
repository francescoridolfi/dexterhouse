// SPDX-License-Identifier: AGPL-3.0-or-later
// Segmented control with a liquid-glass thumb: it springs to the selected tab and stretches
// along the direction of travel while it moves, like a drop of glass sliding on the track.
import { type KeyboardEvent, useCallback, useLayoutEffect, useRef, useState } from "react";

export interface TabItem {
  id: string;
  label: string;
  hidden?: boolean;
}

interface Thumb {
  left: number;
  width: number;
  /** -1 moving left, 1 moving right, 0 at rest (first paint). */
  direction: -1 | 0 | 1;
  /** Bumped on every move to restart the stretch animation. */
  run: number;
}

/** ARIA tabs with arrow-key navigation; scrolls horizontally on narrow windows. */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
  idPrefix = "tab",
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  idPrefix?: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const list = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<Thumb | null>(null);
  const visible = tabs.filter((tab) => !tab.hidden);

  const measure = useCallback(() => {
    const el = refs.current[active];
    if (!el) return;
    setThumb((prev) => {
      const left = el.offsetLeft;
      const width = el.offsetWidth;
      if (prev && prev.left === left && prev.width === width) return prev;
      const direction = !prev ? 0 : left > prev.left ? 1 : left < prev.left ? -1 : 0;
      return { left, width, direction, run: (prev?.run ?? 0) + (direction ? 1 : 0) };
    });
    el.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [active]);

  useLayoutEffect(() => {
    measure();
    const node = list.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(node);
    return () => observer.disconnect();
  }, [measure]);

  const onKey = (event: KeyboardEvent, index: number) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const step = event.key === "ArrowRight" ? 1 : -1;
    const next = visible[(index + step + visible.length) % visible.length];
    if (next) {
      onChange(next.id);
      refs.current[next.id]?.focus();
    }
  };

  return (
    <div
      ref={list}
      role="tablist"
      aria-label={label}
      className="os-segmented relative inline-flex max-w-full gap-0.5 overflow-x-auto rounded-full p-1"
    >
      {thumb ? (
        <span
          aria-hidden
          className="os-liquid-thumb pointer-events-none absolute top-1 bottom-1 rounded-full"
          style={{ left: thumb.left, width: thumb.width }}
        >
          <span
            key={thumb.run}
            className={`absolute inset-0 rounded-full ${
              thumb.direction === 1
                ? "os-liquid-right"
                : thumb.direction === -1
                  ? "os-liquid-left"
                  : ""
            }`}
          />
        </span>
      ) : null}
      {visible.map((tab, index) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            role="tab"
            id={`${idPrefix}-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKey(event, index)}
            className={`relative z-[1] min-h-8 shrink-0 rounded-full px-3.5 text-[13px] font-medium transition-[color,transform] duration-300 ease-(--ease-spring) active:scale-95 ${
              selected ? "text-fg" : "text-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
