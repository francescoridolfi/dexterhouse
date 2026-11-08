// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId,
} from "react";

const CONTROL =
  "w-full rounded-[10px] border border-white/10 bg-black/20 px-3 py-2 text-fg shadow-[inset_0_1px_2px_rgb(0_0_0/0.25)] placeholder:text-muted focus:border-accent focus:ring-3 focus:ring-accent/30 focus:outline-none min-h-11";

function Wrapper({
  label,
  error,
  hint,
  id,
  children,
}: {
  label: string;
  error?: string;
  hint?: ReactNode;
  id: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-failed">
          {error}
        </p>
      ) : null}
    </div>
  );
}

type Common = { label: string; error?: string; hint?: ReactNode };

export function TextField({
  label,
  error,
  hint,
  ...rest
}: Common & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Wrapper label={label} error={error} hint={hint} id={id}>
      <input
        id={id}
        aria-invalid={!!error || undefined}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={CONTROL}
        {...rest}
      />
    </Wrapper>
  );
}

export function TextArea({
  label,
  error,
  hint,
  ...rest
}: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Wrapper label={label} error={error} hint={hint} id={id}>
      <textarea
        id={id}
        aria-invalid={!!error || undefined}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={`${CONTROL} font-mono text-sm`}
        {...rest}
      />
    </Wrapper>
  );
}

export function SelectField({
  label,
  error,
  hint,
  children,
  ...rest
}: Common & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Wrapper label={label} error={error} hint={hint} id={id}>
      <select id={id} aria-invalid={!!error || undefined} className={CONTROL} {...rest}>
        {children}
      </select>
    </Wrapper>
  );
}
