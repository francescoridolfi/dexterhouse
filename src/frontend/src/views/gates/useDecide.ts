// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/client.ts";
import { api, type DecideBody } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import type { Gate } from "../../api/types.ts";

export function useDecide(gate: Gate | undefined, onDone: (next: string) => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DecideBody) => api.decide(gate?.id ?? "", body),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["gates"] });
      void client.invalidateQueries({ queryKey: ["projects"] });
      if (gate) void client.invalidateQueries({ queryKey: keys.gate(gate.id) });
      onDone(result.next ?? "");
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409 && gate) {
        void client.invalidateQueries({ queryKey: keys.gate(gate.id) });
      }
    },
  });
}
