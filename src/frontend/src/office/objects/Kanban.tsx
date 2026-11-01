// SPDX-License-Identifier: AGPL-3.0-or-later
// Kanban post-its on the pm_office board, one column per board column (same as the 2D Board).
// Click → the Board's task drawer.
import { useLayoutEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Color, type InstancedMesh, Matrix4 } from "three";

import type { TaskView } from "../../store/model.ts";
import { BOARD_COLUMNS, boardColumns } from "../../store/selectors.ts";
import type { ColorToken } from "../../theme/tokens.ts";
import { useOffice, useProject } from "../scene/context.ts";
import type { ScenePalette } from "../utils/colors.ts";
import { GEOMETRY, glow } from "../utils/materials.ts";
import { anchor, hoverHandlers } from "./anchors.ts";

const BOARD = anchor("kanban");
const PER_COLUMN = 6;
const MAX = BOARD_COLUMNS.length * PER_COLUMN;
const TONE: Record<string, ColorToken> = {
  backlog: "status-idle",
  ready: "budget-warn",
  in_progress: "status-working",
  in_review: "mode-autonomous",
  in_test: "mode-supervised",
  done: "status-done",
  escalated: "status-failed",
};

export function Kanban({ palette }: { palette: ScenePalette }) {
  const { t } = useTranslation();
  const { runtime, actions } = useOffice();
  const tasks = useProject((s) => s.tasks);
  const notes = useMemo(() => {
    const columns = boardColumns({ tasks });
    return BOARD_COLUMNS.flatMap((column, c) =>
      (columns[column.id] ?? [])
        .slice(-PER_COLUMN)
        .map((task, row) => ({ task, column: column.id, c, row })),
    );
  }, [tasks]);
  const mesh = useRef<InstancedMesh>(null);
  const material = useMemo(() => glow(), []);
  const width = BOARD.prop.w ?? 1;

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const color = new Color();
    notes.forEach((note, i) => {
      const x = BOARD.x - width / 2 + (note.c + 0.5) * (width / BOARD_COLUMNS.length);
      m.setMatrixAt(
        i,
        new Matrix4()
          .makeScale(0.6, 0.16, 0.02)
          .setPosition(x, 1.62 - note.row * 0.2, BOARD.prop.y + 0.18),
      );
      m.setColorAt(i, color.set(palette.token(TONE[note.column] ?? "status-idle")));
    });
    m.count = notes.length;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
  }, [notes, palette, width]);

  const describe = (task: TaskView, column: string) =>
    `${task.external_id} ${task.title}\n${t(`board.column.${column}`)} · ${t("board.iteration", {
      n: task.iteration,
      max: task.max_iterations,
    })}`;

  return (
    <instancedMesh
      ref={mesh}
      args={[GEOMETRY.box, material, MAX]}
      frustumCulled={false}
      onClick={(event) => {
        event.stopPropagation();
        if (event.delta > 4) return; // a drag that pans the view
        const note = notes[event.instanceId ?? -1];
        if (note) actions.openTask(note.task.id);
      }}
      {...hoverHandlers(runtime, (id) => {
        const note = notes[id ?? -1];
        return note ? describe(note.task, note.column) : null;
      })}
    />
  );
}
