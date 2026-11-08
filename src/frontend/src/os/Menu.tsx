// SPDX-License-Identifier: AGPL-3.0-or-later
// Menu bar drop-down: glass panel, closes on Escape, outside click or after a choice.
import { Check } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

export type MenuEntry =
  | {
      label: string;
      onSelect: () => void;
      disabled?: boolean;
      checked?: boolean;
      hint?: string;
    }
  | "separator"
  | { heading: string };

export function Menu({
  label,
  trigger,
  entries,
  className = "",
}: {
  label: string;
  trigger: ReactNode;
  entries: MenuEntry[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    root.current?.querySelector<HTMLElement>("[role^=menuitem]:not([disabled])")?.focus();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onMenuKey = (event: React.KeyboardEvent) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = [
      ...(root.current?.querySelectorAll<HTMLElement>("[role^=menuitem]:not([disabled])") ?? []),
    ];
    const index = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[(index + step + items.length) % items.length]?.focus();
  };

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
        className={`flex h-6 items-center rounded-md px-2.5 text-[13px] ${open ? "bg-white/15" : "hover:bg-white/10"} ${className}`}
      >
        {trigger}
      </button>
      {open ? (
        <div
          id={id}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          className="glass-strong glass-rim os-pop absolute top-7 left-0 z-10 min-w-56 rounded-xl p-1.5 text-[13px]"
        >
          {entries.map((entry, index) => {
            if (entry === "separator")
              return <div key={index} role="separator" className="mx-2 my-1 h-px bg-white/10" />;
            if ("heading" in entry)
              return (
                <div
                  key={index}
                  className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold text-muted"
                >
                  {entry.heading}
                </div>
              );
            return (
              <button
                key={index}
                type="button"
                role={entry.checked === undefined ? "menuitem" : "menuitemradio"}
                aria-checked={entry.checked}
                disabled={entry.disabled}
                onClick={() => {
                  setOpen(false);
                  entry.onSelect();
                }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1 text-left outline-none hover:bg-accent hover:text-white focus-visible:bg-accent focus-visible:text-white disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-fg"
              >
                <span className="grid w-3.5 place-items-center">
                  {entry.checked ? <Check aria-hidden className="size-3.5" /> : null}
                </span>
                <span className="flex-1 truncate">{entry.label}</span>
                {entry.hint ? <span className="text-xs opacity-60">{entry.hint}</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
