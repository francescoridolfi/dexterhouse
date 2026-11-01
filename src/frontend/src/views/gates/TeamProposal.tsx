// SPDX-License-Identifier: AGPL-3.0-or-later
// The Recruiter's proposals at the planning gate (payload.team, E-08): what approving installs.
import { useTranslation } from "react-i18next";

import type { GateTeam } from "../../api/types.ts";

export function TeamProposal({ team }: { team: GateTeam }) {
  const { t } = useTranslation();
  const unreachable = team.marketplace_status !== "reachable";
  return (
    <section aria-labelledby="gate-team" className="space-y-2 pb-3">
      <h3 id="gate-team" className="text-sm font-medium">
        {t("gate.team.title")}
      </h3>
      {unreachable ? (
        <p className="text-xs text-muted">
          {t(`gate.team.status.${team.marketplace_status ?? "unreachable"}`, {
            defaultValue: team.marketplace_status ?? "",
          })}
        </p>
      ) : null}
      {team.proposals.length === 0 ? (
        <p className="text-sm">{t("gate.team.none")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <caption className="sr-only">{t("gate.team.title")}</caption>
            <thead className="text-left text-xs text-muted uppercase">
              <tr>
                <th scope="col" className="py-1">
                  {t("gate.team.package")}
                </th>
                <th scope="col" className="py-1">
                  {t("gate.team.tasks")}
                </th>
                <th scope="col" className="py-1">
                  {t("gate.team.permissions")}
                </th>
                <th scope="col" className="py-1">
                  {t("gate.team.trust")}
                </th>
                <th scope="col" className="py-1">
                  {t("gate.team.reason")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {team.proposals.map((p) => {
                const pinned = `${p.name}@${p.version}`;
                return (
                  <tr key={pinned}>
                    <td className="py-1 font-mono text-xs">
                      {pinned}
                      {team.installed.includes(pinned) ? (
                        <span className="ml-1 text-muted">({t("gate.team.installed")})</span>
                      ) : null}
                    </td>
                    <td className="py-1">{p.for_tasks.join(", ")}</td>
                    <td className="py-1 text-xs">
                      {(p.permissions ?? [])
                        .map((perm) => `${perm.id} (${perm.risk})`)
                        .join(", ") || "—"}
                    </td>
                    <td className="py-1 text-xs">
                      {p.verified ? t("gate.team.verified") : t("gate.team.unverified")} ·{" "}
                      {t("gate.team.risk", { risk: p.risk })} · {p.author_github}
                    </td>
                    <td className="py-1">{p.reason}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {team.summary ? <p className="text-xs text-muted">{team.summary}</p> : null}
    </section>
  );
}
