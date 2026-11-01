// SPDX-License-Identifier: AGPL-3.0-or-later
import { BellRing } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { ErrorState, LoadingBlock } from "../../components/Feedback.tsx";
import { Tabs } from "../../components/Tabs.tsx";
import { useProjectStore } from "../../store/projectStore.ts";
import { primaryGate } from "../../store/selectors.ts";
import { GatePanel } from "../gates/GatePanel.tsx";
import { ForbiddenPage, NotFoundPage } from "../system/Pages.tsx";
import { ProjectHeader } from "./ProjectHeader.tsx";
import { ArtifactsTab } from "./tabs/ArtifactsTab.tsx";
import { BoardTab } from "./tabs/BoardTab.tsx";
import { CostsTab } from "./tabs/CostsTab.tsx";
import { LogTab } from "./tabs/LogTab.tsx";
import { OfficeTab } from "./tabs/OfficeTab.tsx";
import { OverviewTab } from "./tabs/OverviewTab.tsx";
import { TeamTab } from "./tabs/TeamTab.tsx";
import { useProjectStream } from "./useProjectStream.ts";

const TABS = ["overview", "board", "team", "artifacts", "log", "costs", "office"] as const;
type Tab = (typeof TABS)[number];
const SHORTCUTS: Record<string, Tab> = { l: "log", b: "board" };

function GateBanner({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const gate = useProjectStore(primaryGate);
  const budget = useProjectStore((s) => s.budget);
  return (
    <div aria-live="assertive" className="space-y-2">
      {gate ? (
        <div className="flex flex-wrap items-center gap-3 rounded-card border-2 border-blocked bg-blocked/10 p-3">
          <BellRing aria-hidden className="size-5 text-blocked" />
          <p className="flex-1 text-sm">
            <strong className="mr-1 uppercase">{t("gate.openBanner")}:</strong>
            {t(`gate.type.${gate.type}`)} — {gate.title}
          </p>
          <button
            type="button"
            onClick={() => onOpen(gate.id)}
            className="min-h-11 rounded-card bg-blocked px-4 font-medium text-black"
          >
            {t("gate.openPanel")}
          </button>
        </div>
      ) : null}
      {budget.warning && !budget.exceeded ? (
        <p role="status" className="rounded-card bg-budget-warn/15 p-2 text-sm">
          {t("budget.warningBanner")}
        </p>
      ) : null}
    </div>
  );
}

export function ProjectPage() {
  const { t } = useTranslation();
  const { projectId = "", tab = "overview" } = useParams();
  const navigate = useNavigate();
  const { socket, error } = useProjectStream(projectId);
  const loaded = useProjectStore((s) => s.snapshotLoaded && s.projectId === projectId);
  const firstGate = useProjectStore((s) => primaryGate(s)?.id ?? null);
  const [gateId, setGateId] = useState<string | null>(null);
  const active: Tab = (TABS as readonly string[]).includes(tab) ? (tab as Tab) : "overview";
  // Once opened, the office stays mounted (5 fps behind the 2D tabs) to keep its state.
  const [officeOpened, setOfficeOpened] = useState<string | null>(null);
  if (active === "office" && officeOpened !== projectId) setOfficeOpened(projectId);
  const go = (next: string) =>
    void navigate(
      next === "overview" ? `/projects/${projectId}` : `/projects/${projectId}/${next}`,
    );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "g" && firstGate) setGateId(firstGate);
      const destination = SHORTCUTS[event.key];
      if (destination) void navigate(`/projects/${projectId}/${destination}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [firstGate, navigate, projectId]);

  if (error instanceof ApiError && error.status === 404) return <NotFoundPage />;
  if (error instanceof ApiError && error.status === 403) return <ForbiddenPage />;
  if (error && !loaded)
    return <ErrorState error={error} onRetry={() => window.location.reload()} />;
  if (!loaded) return <LoadingBlock rows={6} />;

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <ProjectHeader />
      <GateBanner onOpen={setGateId} />
      <Tabs
        label={t("project.tabs")}
        tabs={TABS.map((id) => ({
          id,
          label: t(`project.tab.${id}`),
          hidden: id === "office" && typeof window !== "undefined" && window.innerWidth < 768,
        }))}
        active={active}
        onChange={go}
        idPrefix="project"
      />
      {active !== "office" ? (
        <div role="tabpanel" id={`project-panel-${active}`} aria-labelledby={`project-${active}`}>
          {active === "overview" ? <OverviewTab socket={socket} onOpenGate={setGateId} /> : null}
          {active === "board" ? <BoardTab /> : null}
          {active === "team" ? <TeamTab /> : null}
          {active === "artifacts" ? <ArtifactsTab /> : null}
          {active === "log" ? <LogTab /> : null}
          {active === "costs" ? <CostsTab /> : null}
        </div>
      ) : null}
      {officeOpened === projectId ? (
        <div
          role="tabpanel"
          id="project-panel-office"
          aria-labelledby="project-office"
          hidden={active !== "office"}
        >
          <OfficeTab active={active === "office"} onOpenGate={setGateId} />
        </div>
      ) : null}
      {gateId ? <GatePanel gateId={gateId} onClose={() => setGateId(null)} /> : null}
    </div>
  );
}
