// SPDX-License-Identifier: AGPL-3.0-or-later
// Desktop widgets (behind the windows): greeting clock and the decisions waiting for you.
import { BellRing, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useMe, useOpenGates } from "../api/queries.ts";
import { useNow } from "../utils/useNow.ts";

function ClockWidget() {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const now = useNow(15_000);
  if (now === 0) return null;
  const date = new Date(now);
  const locale = i18n.language === "it" ? "it-IT" : "en-GB";
  const hour = date.getHours();
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  return (
    <div className="glass glass-rim rounded-[22px] p-5">
      <p className="text-sm text-muted">
        {t(`os.greeting.${part}`, { name: me.data?.display_name ?? "" })}
      </p>
      <p className="mt-1 text-6xl font-extralight tracking-tight tabular-nums">
        {date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
      </p>
      <p className="mt-1 text-sm text-muted capitalize">
        {date.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long" })}
      </p>
    </div>
  );
}

function DecisionsWidget() {
  const { t } = useTranslation();
  const gates = useOpenGates();
  const open = gates.data?.results ?? [];
  return (
    <div className="glass glass-rim rounded-[22px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-b from-[#ffb340] to-[#f06a1d]">
          <BellRing aria-hidden className="size-4 text-white" />
        </span>
        {t("os.widget.decisions")}
        <span className="ml-auto text-2xl font-light tabular-nums">{open.length}</span>
      </div>
      <div className="mt-3 space-y-1.5 text-sm">
        {open.length === 0 ? <p className="text-muted">{t("os.widget.none")}</p> : null}
        {open.slice(0, 3).map((gate) => (
          <p key={gate.id} className="truncate rounded-lg bg-white/5 px-2.5 py-1.5">
            {gate.payload.title}
          </p>
        ))}
      </div>
      <Link
        to="/inbox"
        className="mt-3 flex items-center gap-1 text-sm font-medium text-accent hover:underline"
      >
        {t("os.widget.openInbox")}
        <ChevronRight aria-hidden className="size-4" />
      </Link>
    </div>
  );
}

export function Widgets() {
  return (
    <aside className="pointer-events-auto absolute top-12 right-5 hidden w-72 space-y-4 lg:block">
      <ClockWidget />
      <DecisionsWidget />
    </aside>
  );
}
