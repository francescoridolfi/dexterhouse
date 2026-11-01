// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Gate } from "../../api/types.ts";

/** The escalation opened at 100 % of the budget (F-012): resolved by raising the budget.
 * `budget` is E-10's gate, `budget_exceeded` the reason used by E-06's `escalate()`. */
export const isBudgetGate = (gate: Gate) =>
  gate.payload.reason === "budget_exceeded" ||
  (gate.gate_id === "budget" && gate.payload.reason === "budget");
