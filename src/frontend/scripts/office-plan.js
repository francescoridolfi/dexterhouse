// SPDX-License-Identifier: AGPL-3.0-or-later
// Writes src/office/rooms/office.json (ux/office_layout.md): `node scripts/office-plan.js`.
// Each room owns its top row and left column as walls; the grid's last column and row close
// the plan. Doors are wall cells left open. Walls are stored as run-length encoding.
import { writeFileSync } from "node:fs";

const W = 40;
const H = 30;

const seat = (x, y, facing) => ({ x, y, facing });
const prop = (model, x, y, extra = {}) => ({ model, x, y, rot: 0, ...extra });

const rooms = [
  {
    id: "archive",
    label: { en: "Archive", it: "Archivio" },
    rect: { x: 0, y: 0, w: 10, h: 6 },
    capacity: 0,
    seats: [],
    props: [
      prop("dh/shelf", 2, 1),
      prop("dh/shelf", 4, 1),
      prop("dh/shelf", 6, 1),
      prop("dh/shelf", 8, 1),
      prop("dh/table", 5, 4, { w: 2, bind: "documents" }),
    ],
    light: { color_token: "room.archive", bind: "phase_light" },
  },
  {
    id: "reception",
    label: { en: "Reception", it: "Reception" },
    rect: { x: 10, y: 0, w: 10, h: 12 },
    capacity: 2,
    seats: [seat(14, 4, "S"), seat(17, 4, "S")],
    props: [
      prop("dh/counter", 14, 5, { w: 4 }),
      prop("dh/bell", 16, 5, { bind: "bell" }),
      prop("dh/budget_lamp", 14, 5, { bind: "budget_lamp" }),
      prop("dh/plant", 19, 1),
      prop("dh/plant", 11, 1),
      prop("dh/sofa", 18, 9, { w: 2 }),
    ],
    light: { color_token: "room.reception", bind: "phase_light" },
  },
  {
    id: "meeting_room",
    label: { en: "Meeting room", it: "Sala riunioni" },
    rect: { x: 20, y: 0, w: 20, h: 6 },
    capacity: 8,
    seats: [
      seat(27, 1, "S"),
      seat(29, 1, "S"),
      seat(31, 1, "S"),
      seat(33, 1, "S"),
      seat(27, 5, "N"),
      seat(29, 5, "N"),
      seat(31, 5, "N"),
      seat(33, 5, "N"),
    ],
    props: [
      prop("dh/table_oval", 26, 2, { w: 8, h: 3, bind: "documents" }),
      prop("dh/whiteboard", 38, 2, { h: 3 }),
      prop("dh/plant", 21, 1),
    ],
    light: { color_token: "room.meeting", bind: "phase_light" },
  },
  {
    id: "design_studio",
    label: { en: "Design studio", it: "Studio di progettazione" },
    rect: { x: 20, y: 6, w: 20, h: 6 },
    capacity: 4,
    seats: [seat(25, 9, "N"), seat(26, 9, "N"), seat(33, 9, "N"), seat(34, 9, "N")],
    props: [
      prop("dh/drafting_table", 25, 8, { w: 2 }),
      prop("dh/desk", 33, 8, { w: 2 }),
      prop("dh/whiteboard", 38, 8, { h: 3 }),
      prop("dh/table", 28, 10, { bind: "documents" }),
      prop("dh/poster", 36, 7),
    ],
    light: { color_token: "room.design", bind: "phase_light" },
  },
  {
    id: "hr_office",
    label: { en: "HR office", it: "Ufficio HR" },
    rect: { x: 0, y: 6, w: 10, h: 6 },
    capacity: 2,
    seats: [seat(4, 9, "N"), seat(5, 9, "N")],
    props: [
      prop("dh/desk", 4, 8, { w: 2 }),
      prop("dh/agent_door", 1, 10),
      prop("dh/package_box", 7, 10, { bind: "package_box" }),
      prop("dh/plant", 9, 7),
    ],
    light: { color_token: "room.hr", bind: "phase_light" },
  },
  {
    id: "pm_office",
    label: { en: "PM office", it: "Ufficio PM" },
    rect: { x: 0, y: 12, w: 14, h: 6 },
    capacity: 2,
    seats: [seat(5, 15, "N"), seat(8, 15, "N")],
    props: [
      prop("dh/kanban_board", 3, 13, { w: 7, bind: "kanban" }),
      prop("dh/plant", 1, 17),
      prop("dh/shelf", 12, 13),
    ],
    light: { color_token: "room.pm", bind: "phase_light" },
  },
  {
    id: "open_space",
    label: { en: "Open space", it: "Open space" },
    rect: { x: 14, y: 12, w: 26, h: 12 },
    capacity: 12,
    seats: [18, 24, 30].flatMap((x) => [
      seat(x, 15, "S"),
      seat(x + 1, 15, "S"),
      seat(x, 18, "N"),
      seat(x + 1, 18, "N"),
    ]),
    props: [
      ...[18, 24, 30].flatMap((x) => [
        prop("dh/desk", x, 16, { w: 2 }),
        prop("dh/desk", x, 17, { w: 2 }),
      ]),
      ...[18, 24, 30].flatMap((x) =>
        [16, 17].flatMap((y) => [
          prop("dh/pc", x, y, { bind: "workspace_pc" }),
          prop("dh/pc", x + 1, y, { bind: "workspace_pc" }),
        ]),
      ),
      prop("dh/table", 36, 21, { bind: "documents" }),
      prop("dh/plant", 38, 13),
      prop("dh/plant", 15, 23),
    ],
    light: { color_token: "room.open", bind: "phase_light" },
  },
  {
    id: "review_corner",
    label: { en: "Review corner", it: "Angolo review" },
    rect: { x: 0, y: 18, w: 14, h: 6 },
    capacity: 3,
    seats: [seat(9, 21, "N"), seat(10, 21, "N"), seat(11, 21, "N")],
    props: [
      prop("dh/big_monitor", 9, 19, { w: 3 }),
      prop("dh/lamp", 13, 19),
      prop("dh/armchair", 2, 22),
      prop("dh/table", 4, 20, { bind: "documents" }),
    ],
    light: { color_token: "room.review", bind: "phase_light" },
  },
  {
    id: "qa_lab",
    label: { en: "QA Lab", it: "Laboratorio QA" },
    rect: { x: 0, y: 24, w: 14, h: 5 },
    capacity: 3,
    seats: [seat(3, 26, "N"), seat(6, 26, "N"), seat(9, 26, "N")],
    props: [
      prop("dh/desk_lab", 3, 25),
      prop("dh/desk_lab", 6, 25),
      prop("dh/desk_lab", 9, 25),
      prop("dh/traffic_light", 12, 25, { bind: "test_light" }),
      prop("dh/rack", 1, 28),
      prop("dh/table", 6, 28, { bind: "documents" }),
    ],
    light: { color_token: "room.qa", bind: "phase_light" },
  },
  {
    id: "break_room",
    label: { en: "Break room", it: "Area relax" },
    rect: { x: 14, y: 24, w: 12, h: 5 },
    capacity: 12,
    seats: [16, 17, 18, 22, 23, 24].flatMap((x) => [seat(x, 26, "S"), seat(x, 28, "N")]),
    props: [
      prop("dh/coffee_table", 16, 27, { w: 3 }),
      prop("dh/coffee_table", 22, 27, { w: 3 }),
      prop("dh/coffee_machine", 15, 25),
      prop("dh/pinball", 25, 28),
    ],
    light: { color_token: "room.break", bind: "phase_light" },
  },
  {
    id: "release_dock",
    label: { en: "Release dock", it: "Banchina di rilascio" },
    rect: { x: 26, y: 24, w: 14, h: 5 },
    capacity: 4,
    seats: [seat(29, 26, "E"), seat(30, 26, "E"), seat(29, 28, "E"), seat(30, 28, "E")],
    props: [
      prop("dh/dock_door", 38, 26, { h: 2 }),
      prop("dh/conveyor", 33, 27, { w: 4 }),
      prop("dh/dock_light", 37, 25, { bind: "dock_light" }),
      prop("dh/crate", 37, 28),
      prop("dh/crate", 28, 25),
    ],
    light: { color_token: "room.dock", bind: "phase_light" },
  },
];

// Every door joins two rooms (or the reception and the street, at the exit).
const DOORS = [
  [12, 0],
  [10, 3],
  [10, 9],
  [20, 3],
  [20, 9],
  [30, 6],
  [12, 12],
  [16, 12],
  [30, 12],
  [14, 15],
  [6, 18],
  [14, 21],
  [14, 26],
  [20, 24],
  [26, 26],
  [32, 24],
];
const touches = ({ rect }, x, y) =>
  x >= rect.x &&
  x <= rect.x + rect.w &&
  y >= rect.y &&
  y <= rect.y + rect.h &&
  (x === rect.x || y === rect.y || x === rect.x + rect.w || y === rect.y + rect.h) &&
  !((x === rect.x || x === rect.x + rect.w) && (y === rect.y || y === rect.y + rect.h));
for (const room of rooms) {
  room.doors = DOORS.filter(([x, y]) => touches(room, x, y)).map(([x, y]) => ({ x, y }));
}

const walls = new Uint8Array(W * H);
const set = (x, y, v) => (walls[y * W + x] = v);
for (const { rect } of rooms) {
  for (let x = rect.x; x < rect.x + rect.w; x++) set(x, rect.y, 1);
  for (let y = rect.y; y < rect.y + rect.h; y++) set(rect.x, y, 1);
}
for (let y = 0; y < H; y++) set(W - 1, y, 1);
for (let x = 0; x < W; x++) set(x, H - 1, 1);
for (const [x, y] of DOORS) set(x, y, 0);

const runs = [];
let current = 0;
let length = 0;
for (const cell of walls) {
  if (cell === current) length++;
  else {
    runs.push(length);
    current = cell;
    length = 1;
  }
}
runs.push(length);

const plan = {
  schema: 1,
  grid: { w: W, h: H, cell_m: 1.0 },
  rooms,
  walls: `rle:${runs.join(",")}`,
  spawn: { x: 12, y: 10 },
  exit: { x: 12, y: 0 },
};
const out = new URL("../src/office/rooms/office.json", import.meta.url);
writeFileSync(out, `${JSON.stringify(plan, null, 2)}\n`);
console.log(`wrote ${out.pathname}: ${rooms.length} rooms, ${runs.length} runs`);
