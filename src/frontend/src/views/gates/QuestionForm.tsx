// SPDX-License-Identifier: AGPL-3.0-or-later
import type { UseMutationResult } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import type { DecideBody } from "../../api/endpoints.ts";
import type { Gate, Question } from "../../api/types.ts";
import { Button } from "../../components/Button.tsx";

type Decide = UseMutationResult<Gate, Error, DecideBody>;
const OTHER = "__other__";

function kindOf(q: Question): "text" | "choice" | "boolean" {
  if (q.kind === "boolean") return "boolean";
  return q.kind === "choice" || (q.options?.length ?? 0) > 0 ? "choice" : "text";
}

/** Flow F3: "send answers" only when every question has an answer. */
export function QuestionForm({
  gate,
  decide,
  disabled,
}: {
  gate: Gate;
  decide: Decide;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const questions = gate.payload.questions ?? [];
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries((gate.answers ?? []).map((a) => [a.question_id, a.answer])),
  );
  const [other, setOther] = useState<Record<string, string>>({});
  const value = (q: Question) =>
    answers[q.id] === OTHER ? (other[q.id] ?? "") : (answers[q.id] ?? "");
  const complete = questions.every((q) => value(q).trim() !== "");
  const set = (id: string, v: string) => setAnswers((a) => ({ ...a, [id]: v }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    decide.mutate({ answers: questions.map((q) => ({ question_id: q.id, answer: value(q) })) });
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <fieldset disabled={disabled} className="space-y-4">
        {questions.map((q, index) => (
          <div key={q.id} className="space-y-2 rounded-card border border-line p-3">
            <p id={`q-${q.id}`} className="text-sm font-medium">
              {index + 1}. {q.text}
            </p>
            {kindOf(q) === "choice" ? (
              <div role="radiogroup" aria-labelledby={`q-${q.id}`} className="space-y-1 text-sm">
                {[...(q.options ?? []), OTHER].map((option) => (
                  <label key={option} className="flex min-h-9 items-center gap-2">
                    <input
                      type="radio"
                      name={q.id}
                      checked={answers[q.id] === option}
                      onChange={() => set(q.id, option)}
                    />
                    {option === OTHER ? t("gate.other") : option}
                  </label>
                ))}
                {answers[q.id] === OTHER ? (
                  <input
                    aria-label={t("gate.other")}
                    value={other[q.id] ?? ""}
                    onChange={(e) => setOther((o) => ({ ...o, [q.id]: e.target.value }))}
                    className="min-h-11 w-full rounded-card border border-line bg-bg px-2"
                  />
                ) : null}
              </div>
            ) : kindOf(q) === "boolean" ? (
              <div role="radiogroup" aria-labelledby={`q-${q.id}`} className="flex gap-4 text-sm">
                {["yes", "no"].map((option) => (
                  <label key={option} className="flex min-h-9 items-center gap-2">
                    <input
                      type="radio"
                      name={q.id}
                      checked={answers[q.id] === t(`gate.${option}`)}
                      onChange={() => set(q.id, t(`gate.${option}`))}
                    />
                    {t(`gate.${option}`)}
                  </label>
                ))}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                <input
                  aria-labelledby={`q-${q.id}`}
                  value={answers[q.id] ?? ""}
                  placeholder={q.default_assumption ?? ""}
                  onChange={(e) => set(q.id, e.target.value)}
                  className="min-h-11 flex-1 rounded-card border border-line bg-bg px-2 text-sm"
                />
                {q.default_assumption ? (
                  <Button size="sm" onClick={() => set(q.id, q.default_assumption ?? "")}>
                    {t("gate.useAssumption")}
                  </Button>
                ) : null}
              </div>
            )}
          </div>
        ))}
      </fieldset>
      {!disabled ? (
        <div className="flex justify-end">
          <Button type="submit" variant="primary" disabled={!complete} busy={decide.isPending}>
            {t("gate.sendAnswers")}
          </Button>
        </div>
      ) : null}
    </form>
  );
}
