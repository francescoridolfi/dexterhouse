// SPDX-License-Identifier: AGPL-3.0-or-later
// Toasts for action results (title + detail from problem+json).
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useToasts } from "./toastStore.ts";

const TONES = { info: "bg-accent", success: "bg-done", error: "bg-failed" };

export function Toaster() {
  const { t } = useTranslation();
  const { toasts, dismiss } = useToasts();
  return (
    <div
      aria-live="polite"
      className="fixed top-10 right-3 z-[1100] flex w-80 max-w-[calc(100vw-1.5rem)] flex-col gap-2"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.tone === "error" ? "alert" : "status"}
          className="glass glass-rim os-pop flex items-start gap-3 rounded-[18px] p-3"
        >
          <span
            aria-hidden
            className={`mt-1.5 size-2 shrink-0 rounded-full ${TONES[toast.tone]}`}
          />
          <div className="flex-1">
            <p className="text-sm font-medium">{toast.title}</p>
            {toast.detail ? <p className="mt-0.5 text-xs text-muted">{toast.detail}</p> : null}
          </div>
          <button
            type="button"
            aria-label={t("close")}
            onClick={() => dismiss(toast.id)}
            className="text-muted"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
