// SPDX-License-Identifier: AGPL-3.0-or-later
// Office tab: the R3F bundle is loaded only from here (code splitting, ADR-0007). Without
// WebGL 2, or under 20 fps for 10 s, the tab shows the 2D team view with a notice and a retry.
import { Box } from "lucide-react";
import { Suspense, lazy, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Button } from "../../../components/Button.tsx";
import { LoadingBlock } from "../../../components/Feedback.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { officeDescription } from "../../../store/selectors.ts";
import { hasWebGL2 } from "../../../utils/webgl.ts";
import { TeamNow } from "../panels/TeamNow.tsx";

const OfficeView = lazy(() => import("../../../office/OfficeView.tsx"));

type Mode = "3d" | "no-webgl" | "slow";

function Fallback({ mode, onRetry }: { mode: Exclude<Mode, "3d">; onRetry: () => void }) {
  const { t } = useTranslation();
  const description = useProjectStore(officeDescription);
  return (
    <div className="space-y-4">
      <div
        role="status"
        className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface p-4"
      >
        <Box aria-hidden className="size-5 text-muted" />
        <p className="flex-1 text-sm">{t(`office.fallback.${mode}`)}</p>
        <Button onClick={onRetry}>{t("office.fallback.retry")}</Button>
      </div>
      <p role="img" aria-label={description} className="text-sm text-muted">
        {description}
      </p>
      <TeamNow />
    </div>
  );
}

export function OfficeTab({
  active = true,
  onOpenGate,
}: {
  active?: boolean;
  onOpenGate: (gateId: string) => void;
}) {
  const [mode, setMode] = useState<Mode>(() => (hasWebGL2() ? "3d" : "no-webgl"));
  const [params] = useSearchParams();
  const at = params.get("replay");
  const replayAt = at && !Number.isNaN(Date.parse(at)) ? Date.parse(at) : null;
  if (mode !== "3d") {
    return <Fallback mode={mode} onRetry={() => setMode(hasWebGL2() ? "3d" : "no-webgl")} />;
  }
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <OfficeView
        active={active}
        onSlow={() => setMode("slow")}
        onOpenGate={onOpenGate}
        replayAt={replayAt}
      />
    </Suspense>
  );
}
