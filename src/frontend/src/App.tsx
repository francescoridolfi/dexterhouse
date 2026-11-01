// SPDX-License-Identifier: AGPL-3.0-or-later
import { CoreStatus } from "./views/dashboard/index.ts";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-xl font-semibold tracking-tight">DexterHouse</h1>
        <p className="text-sm text-slate-400">An open-source software house of AI agents</p>
      </header>
      <main className="px-6 py-8">
        <CoreStatus />
      </main>
    </div>
  );
}
