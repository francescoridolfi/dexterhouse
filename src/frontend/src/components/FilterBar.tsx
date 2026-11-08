// SPDX-License-Identifier: AGPL-3.0-or-later
// Recessed glass filter bar (Projects, Log): search first, then filter pills. Narrow windows
// stack the search above the pills; from @xl everything sits on one row.
import { ChevronDown, Search } from "lucide-react";
import type { ReactNode } from "react";

export function FilterBar({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="search"
      className={`flex flex-col gap-1.5 rounded-[16px] border border-line bg-black/20 p-1.5 shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)] @xl:flex-row @xl:items-center ${className}`}
    >
      {children}
    </div>
  );
}

/** The filter pills, kept together; they share the row and wrap when there are many. */
export function FilterGroup({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-1.5">{children}</div>;
}

export function SearchField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative min-w-0 flex-1">
      <Search
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
      />
      <input
        type="search"
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-[11px] bg-transparent pr-3 pl-9 text-sm placeholder:text-muted hover:bg-white/5 focus:bg-white/8 focus:outline-none"
      />
    </div>
  );
}

/** Pill around a native select; tinted with the accent while a filter is active. */
export function FilterSelect({
  id,
  label,
  icon,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  icon: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  const active = value !== "";
  return (
    <div className="relative min-w-32 flex-1 @xl:flex-none">
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <span
        className={`pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 ${active ? "text-accent" : "text-muted"}`}
      >
        {icon}
      </span>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`h-9 w-full appearance-none truncate rounded-[11px] pr-8 pl-8 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent @xl:max-w-56 ${
          active
            ? "bg-accent/18 text-accent hover:bg-accent/25"
            : "bg-white/6 text-fg hover:bg-white/10"
        }`}
      >
        {options.map(([optionValue, text]) => (
          <option key={optionValue} value={optionValue}>
            {text}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted"
      />
    </div>
  );
}
