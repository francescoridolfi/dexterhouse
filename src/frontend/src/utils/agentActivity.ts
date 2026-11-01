// SPDX-License-Identifier: AGPL-3.0-or-later
// What one agent did, from the events in the store (agent panel in the Team tab and the 3D).
import type { EventEnvelope } from "../api/types.ts";

export interface AgentActivity {
  /** Newest first, at most `limit`. */
  recent: EventEnvelope[];
  tools: { tool: string; count: number }[];
  cost: number;
  turns: number;
  currentTurn: { turnId: string; startedAt: string; inputTokensEst: number | null } | null;
}

export function agentActivity(
  events: EventEnvelope[],
  agentId: string,
  turnId: string | null,
  limit = 10,
): AgentActivity {
  const turns = new Set<string>();
  const mine: EventEnvelope[] = [];
  const tools = new Map<string, number>();
  let cost = 0;
  let current: AgentActivity["currentTurn"] = null;
  for (const event of events) {
    const p = event.payload ?? {};
    const turn = typeof p.turn_id === "string" ? p.turn_id : null;
    if (event.type === "agent.turn.started" && p.agent_id === agentId && turn) {
      turns.add(turn);
      if (turn === turnId) {
        const context = p.context as { input_tokens_est?: unknown } | undefined;
        current = {
          turnId: turn,
          startedAt: event.created_at,
          inputTokensEst:
            typeof context?.input_tokens_est === "number" ? context.input_tokens_est : null,
        };
      }
    }
    const own = p.agent_id === agentId || event.actor.id === agentId || (turn && turns.has(turn));
    if (!own) continue;
    mine.push(event);
    if (event.type === "agent.tool.used" && typeof p.tool === "string") {
      tools.set(p.tool, (tools.get(p.tool) ?? 0) + 1);
    }
    if (event.type === "agent.turn.completed" && p.agent_id === agentId)
      cost += Number(p.cost) || 0;
  }
  return {
    recent: mine.slice(-limit).reverse(),
    tools: [...tools.entries()]
      .map(([tool, count]) => ({ tool, count }))
      .sort((a, b) => b.count - a.count || a.tool.localeCompare(b.tool)),
    cost,
    turns: turns.size,
    currentTurn: current,
  };
}
