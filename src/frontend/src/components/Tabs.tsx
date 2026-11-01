// SPDX-License-Identifier: AGPL-3.0-or-later
import { type KeyboardEvent, useRef } from "react";

export interface TabItem {
  id: string;
  label: string;
  hidden?: boolean;
}

/** ARIA tabs with arrow-key navigation; scrolls horizontally on narrow screens. */
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
  const visible = tabs.filter((tab) => !tab.hidden);
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
      role="tablist"
      aria-label={label}
      className="flex gap-1 overflow-x-auto border-b border-line"
    >
      {visible.map((tab, index) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
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
            className={`min-h-11 shrink-0 border-b-2 px-3 text-sm font-medium ${
              selected ? "border-accent text-accent" : "border-transparent text-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
