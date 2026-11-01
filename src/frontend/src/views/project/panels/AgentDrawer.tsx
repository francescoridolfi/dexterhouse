// SPDX-License-Identifier: AGPL-3.0-or-later
// Team tab: the agent panel in the right drawer (lazy, like the 3D side panel's content).
import { Drawer } from "../../../components/Overlay.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { AgentDetails } from "./AgentPanel.tsx";

export default function AgentDrawer({
  agentId,
  spent,
  onOpenTurn,
  onClose,
}: {
  agentId: string;
  spent?: string;
  onOpenTurn: (turnId: string) => void;
  onClose: () => void;
}) {
  const agent = useProjectStore((s) => s.agents[agentId]);
  const events = useProjectStore((s) => s.events);
  const tasks = useProjectStore((s) => s.tasks);
  if (!agent) return null;
  return (
    <Drawer title={agent.displayName} onClose={onClose}>
      <AgentDetails
        agent={agent}
        events={events}
        tasks={tasks}
        spent={spent}
        onOpenTurn={onOpenTurn}
      />
    </Drawer>
  );
}
