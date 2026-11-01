// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Spinner } from "./Feedback.tsx";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:brightness-110",
  secondary: "border border-line bg-surface text-fg hover:bg-bg",
  danger: "bg-failed text-white hover:brightness-110",
  ghost: "text-fg hover:bg-bg",
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
      className={`inline-flex items-center justify-center gap-2 rounded-card font-medium transition-[filter,background] duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${height} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Spinner /> : icon}
      {children}
    </button>
  );
}
