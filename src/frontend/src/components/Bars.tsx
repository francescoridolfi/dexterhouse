// SPDX-License-Identifier: AGPL-3.0-or-later
// Single-series horizontal bars with the value written next to each bar (no colour coding).
export interface Bar {
  key: string;
  label: string;
  value: number;
  display: string;
}

export function Bars({ bars, label }: { bars: Bar[]; label: string }) {
  const max = Math.max(...bars.map((b) => b.value), 0);
  return (
    <ul aria-label={label} className="space-y-1.5">
      {bars.map((bar) => (
        <li
          key={bar.key}
          className="grid grid-cols-[minmax(6rem,10rem)_1fr_5.5rem] items-center gap-2 text-sm"
        >
          <span className="truncate">{bar.label}</span>
          <span aria-hidden className="h-3 rounded bg-line">
            <span
              className="block h-full rounded bg-accent"
              style={{ width: `${max > 0 ? Math.max(2, (bar.value / max) * 100) : 0}%` }}
            />
          </span>
          <span className="text-right font-mono text-xs">{bar.display}</span>
        </li>
      ))}
    </ul>
  );
}
