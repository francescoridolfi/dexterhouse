// SPDX-License-Identifier: AGPL-3.0-or-later
// Right-hand drawer (gate panel, task drawer, turn detail) and confirmation dialog.
import { X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button.tsx";

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

/** 480–640 px from the right on desktop, full screen below 1024 px (ux_2d_states.md). */
export function Drawer({
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  useEscape(onClose);
  useEffect(() => {
    panel.current?.focus();
  }, []);
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div aria-hidden="true" className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        tabIndex={-1}
        className={`relative flex h-full w-full flex-col bg-surface shadow-xl lg:w-[480px] ${wide ? "xl:w-[640px]" : ""}`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line p-4">
          <h2 id={id} className="text-lg font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
            className="grid size-11 shrink-0 place-items-center rounded-card hover:bg-bg"
          >
            <X aria-hidden className="size-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {footer ? <footer className="border-t border-line p-4">{footer}</footer> : null}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  useEscape(onCancel);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div aria-hidden="true" className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={id}
        className="relative w-full max-w-md rounded-card bg-surface p-5 shadow-xl"
      >
        <h2 id={id} className="text-lg font-semibold">
          {title}
        </h2>
        <div className="mt-2 text-sm text-muted">{message}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel} autoFocus>
            {t("cancel")}
          </Button>
          <Button variant={danger ? "danger" : "primary"} busy={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
