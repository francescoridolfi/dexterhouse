// SPDX-License-Identifier: AGPL-3.0-or-later
// Toasts for action results (title + detail from problem+json).
import { create } from "zustand";

import { ApiError } from "../api/client.ts";

export interface Toast {
  id: number;
  tone: "info" | "success" | "error";
  title: string;
  detail?: string;
}

interface ToastStore {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let next = 1;

export const useToasts = create<ToastStore>()((set) => ({
  toasts: [],
  push: (toast) => {
    const id = next++;
    set((state) => ({ toasts: [...state.toasts.slice(-3), { ...toast, id }] }));
    setTimeout(() => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })), 6000);
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

export function toastError(title: string, error: unknown): void {
  const detail = error instanceof ApiError || error instanceof Error ? error.message : undefined;
  useToasts.getState().push({ tone: "error", title, detail });
}

export function toastSuccess(title: string, detail?: string): void {
  useToasts.getState().push({ tone: "success", title, detail });
}
