// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCoreHealth } from "./useCoreHealth.ts";

export function CoreStatus() {
  const health = useCoreHealth();

  let dot: string;
  let label: string;
  switch (health.state) {
    case "loading":
      dot = "bg-slate-500 animate-pulse";
      label = "Checking core…";
      break;
    case "ok":
      dot = "bg-emerald-500";
      label = `Core is up (${health.status})`;
      break;
    case "error":
      dot = "bg-rose-500";
      label = `Core unreachable: ${health.message}`;
      break;
  }

  return (
    <section
      aria-labelledby="core-status-title"
      className="max-w-md rounded-lg border border-slate-800 bg-slate-900 p-4"
    >
      <h2 id="core-status-title" className="text-sm font-medium text-slate-300">
        Core status
      </h2>
      <p
        role="status"
        aria-busy={health.state === "loading"}
        className="mt-2 flex items-center gap-2"
      >
        <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
        <span>{label}</span>
      </p>
    </section>
  );
}
