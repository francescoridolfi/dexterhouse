// SPDX-License-Identifier: AGPL-3.0-or-later
// Drop zone for context documents: drag files in or pick them, listed with a remove button.
// The files are only collected here; the caller uploads them.
import { FileText, Upload, X } from "lucide-react";
import { type DragEvent, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { bytes } from "../utils/format.ts";

export const CONTEXT_ACCEPT = ".pdf,.docx,.md,.markdown,.txt,.json,.yaml,.yml,.csv";

export function FileDrop({
  label,
  files,
  onChange,
  disabled = false,
}: {
  label: string;
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const add = (list: FileList | null) => {
    if (!list) return;
    const known = new Set(files.map((f) => `${f.name}:${f.size}`));
    onChange([...files, ...Array.from(list).filter((f) => !known.has(`${f.name}:${f.size}`))]);
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    if (!disabled) add(event.dataTransfer.files);
  };
  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        className={`flex flex-col items-center gap-2 rounded-[14px] border border-dashed px-4 py-5 text-center text-sm transition-colors ${
          over ? "border-accent bg-accent/10" : "border-white/15 bg-black/15"
        }`}
      >
        <Upload aria-hidden className="size-5 text-muted" />
        <p className="text-muted">{t("context.dropHint")}</p>
        <label
          htmlFor={id}
          className={`os-pressable inline-flex min-h-8 cursor-pointer items-center rounded-full bg-white/8 px-3.5 text-[13px] font-medium hover:bg-white/14 has-focus-visible:outline-2 has-focus-visible:outline-accent ${disabled ? "pointer-events-none opacity-50" : ""}`}
        >
          {label}
          <input
            ref={input}
            id={id}
            type="file"
            multiple
            accept={CONTEXT_ACCEPT}
            disabled={disabled}
            className="sr-only"
            onChange={(e) => {
              add(e.target.files);
              if (input.current) input.current.value = "";
            }}
          />
        </label>
        <p className="text-xs text-muted">{t("context.limits")}</p>
      </div>
      {files.length ? (
        <ul className="space-y-1" aria-label={t("context.selected")}>
          {files.map((file) => (
            <li
              key={`${file.name}:${file.size}`}
              className="flex items-center gap-2 rounded-[10px] bg-white/4 py-1 pr-1 pl-3 text-sm"
            >
              <FileText aria-hidden className="size-4 shrink-0 text-muted" />
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
              <span className="shrink-0 text-xs text-muted tabular-nums">{bytes(file.size)}</span>
              <button
                type="button"
                aria-label={t("context.remove", { name: file.name })}
                disabled={disabled}
                onClick={() => onChange(files.filter((f) => f !== file))}
                className="grid size-7 place-items-center rounded-full text-muted hover:bg-white/10 hover:text-fg"
              >
                <X aria-hidden className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
