# ADR-0007: Frontend SPA with React + React Three Fiber

- Status: accepted · Date: 2026-10-31

## Context
We need a rich UI with a real-time 3D scene and a complex 2D dashboard. The project owner chose a separate SPA.

## Decision
`src/frontend`: Vite + React 18 + TypeScript, React Three Fiber + drei for 3D, Zustand for state, TanStack Query for REST, Tailwind. Static build served by nginx; Django exposes only APIs and WebSockets.

## Alternatives considered
- Django templates + HTMX + vanilla Three.js: fewer moving parts, but state management for the 3D view and the dashboard becomes unmanageable without a framework.
- Babylon.js: excellent engine, but R3F integrates better with React state and has more ready-made examples and assets.
- Godot/Unity web export: great rendering, but complex build pipeline and data integration.

## Consequences
+ One store feeds both 2D and 3D; tests with Vitest/Playwright; simple static deploy.
+ Large R3F community, ready-made CC0 glTF assets.
− Two toolchains (Python and Node) to maintain; pre-commit covers both.
− Heavy 3D bundle: code splitting, the 3D view loads only when requested.

> Implementation note: the 2D dashboard is released; the 3D office is in progress and not released yet.
