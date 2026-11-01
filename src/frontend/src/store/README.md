# Project store

One normalised Zustand store per open project, read by the 2D dashboard and (E-09) the 3D
office. Views never compute domain state themselves: they call the selectors.

- `model.ts`: `ProjectState` — `agents`, `rooms` (room → agent ids), `phases` (by `phase_id`),
  `tasks`, `gates`, `artifacts` (refs seen in events), `events` (last 2 000), `speaking`
  (last stream text per agent), `budget`.
- `reducer.ts`: pure `applySnapshot`, `applyEvent`, `applySpeaking`; unknown event types are
  ignored and counted.
- `socket.ts`: `ProjectSocket` feeds the store from `/ws/projects/{id}` (resync on reconnect).
- `selectors.ts`: board columns, team, open gates, budget level, office description.

The 3D office imports from `store/` only, never from `api/`.
