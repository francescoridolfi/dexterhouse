// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Gate } from "../../api/types.ts";

/** The escalation opened at 100 % of the budget (F-012): resolved by raising the budget. */
export const isBudgetGate = (gate: Gate) =>
  gate.gate_id === "budget" && gate.payload.reason === "budget";
