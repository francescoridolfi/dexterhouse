// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Spinner } from "./Feedback.tsx";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-[#3d9bff] to-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_4px_12px_-4px_rgb(10_132_255/0.6)] hover:brightness-110",
  secondary:
    "border border-white/10 bg-white/8 text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] hover:bg-white/14",
  danger:
    "bg-gradient-to-b from-[#ff6b61] to-[#e5352b] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25)] hover:brightness-110",
  ghost: "text-fg hover:bg-white/10",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  icon?: ReactNode;
  size?: "sm" | "md";
}

/** Touch target ≥ 44 px on `md`; `busy` shows a spinner and disables the button. */
export function Button({
  variant = "secondary",
  busy = false,
  icon,
  size = "md",
  className = "",
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  const height = size === "md" ? "min-h-11 px-4" : "min-h-8 px-2.5 text-sm";
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`os-pressable inline-flex items-center justify-center gap-2 rounded-[10px] font-medium transition-[filter,background] duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${height} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Spinner /> : icon}
      {children}
    </button>
  );
}
