// SPDX-License-Identifier: AGPL-3.0-or-later
// Local fixtures of the Code app and of the `code_graph` artifact (schema 1, the contract
// shared with the core's code-graph generator). Used by the tests and the dev mock.
import type { Artifact, CodeFile, CodeLocation, CodeTree } from "../api/types.ts";

export const PROJECT_ID = "p-1";
export const COMMIT = "3f9c2a7b1d4e5f60718293a4b5c6d7e8f9012345"; // pragma: allowlist secret

export const codeTree: CodeTree = {
  ref: "HEAD",
  commit: COMMIT,
  branch: "main",
  truncated: false,
  entries: [
    { path: "README.md", type: "file", size: 120 },
    { path: "pyproject.toml", type: "file", size: 310 },
    { path: "src/gymbook/__init__.py", type: "file", size: 0 },
    { path: "src/gymbook/api.py", type: "file", size: 812 },
    { path: "src/gymbook/models.py", type: "file", size: 640 },
    { path: "src/gymbook/booking.py", type: "file", size: 905 },
    { path: "tests/test_booking.py", type: "file", size: 420 },
    { path: "assets/logo.png", type: "file", size: 2048 },
  ],
};

export const bookingSource = `from dataclasses import dataclass
from datetime import datetime

from gymbook.models import Member, Slot


@dataclass
class Booking:
    member: Member
    slot: Slot
    created_at: datetime


def book(member: Member, slot: Slot) -> Booking:
    """Reserve a slot; raises when it is full."""
    if slot.is_full():
        raise ValueError("slot is full")
    slot.taken += 1
    return Booking(member, slot, datetime.now())


def cancel(booking: Booking) -> None:
    booking.slot.taken -= 1
`;

export function codeFile(path: string, content = bookingSource): CodeFile {
  return {
    ref: "HEAD",
    commit: COMMIT,
    path,
    size: content.length,
    binary: false,
    too_large: false,
    content,
  };
}

export const codeLocation: CodeLocation = {
  workspace: {
    id: "ws-1",
    status: "idle",
    path: "/workspace",
    volume: "dexterhouse-ws-1",
    container_id: "c0ffee12",
    image: "ghcr.io/francescoridolfi/dexterhouse-workspace-python:0.1.0",
  },
  branch: "main",
  head: {
    commit: COMMIT,
    author: "DexterHouse",
    date: "2026-11-14T10:00:00Z",
    message: "merge(task/T-04): booking rules",
  },
  unavailable: null,
  remote_url: "https://github.com/acme/gymbook.git",
  web_url: "https://github.com/acme/gymbook",
  delivery_mode: "pull_request",
  releases: [
    {
      number: 1,
      mode: "pull_request",
      branch: "dexterhouse/release-1",
      commit: COMMIT,
      pr_url: "https://github.com/acme/gymbook/pull/1",
      remote_url: "https://github.com/acme/gymbook.git",
      delivered_at: "2026-11-14T10:05:00Z",
    },
  ],
};

const file = (path: string, community: number) => ({
  id: `file:${path}`,
  kind: "file",
  label: path.split("/").pop()!,
  path,
  lang: "python",
  line: null,
  symbol_kind: null,
  parent: null,
  community,
});

const symbol = (path: string, name: string, line: number, kind: string, community: number) => ({
  id: `sym:${path}:${name}`,
  kind: "symbol",
  label: name,
  path,
  lang: "python",
  line,
  symbol_kind: kind,
  parent: `file:${path}`,
  community,
});

/** `code_graph` data, schema 1. */
export const codeGraphData = {
  schema: 1,
  commit: COMMIT,
  generated_at: "2026-11-14T10:01:00Z",
  stats: { files: 5, symbols: 7, edges: 17 },
  nodes: [
    file("src/gymbook/api.py", 0),
    file("src/gymbook/models.py", 1),
    file("src/gymbook/booking.py", 0),
    file("tests/test_booking.py", 2),
    { id: "mod:gymbook", kind: "module", label: "gymbook", path: "src/gymbook", community: 0 },
    { id: "ext:fastapi", kind: "external", label: "fastapi", community: 3 },
    { id: "ext:datetime", kind: "external", label: "datetime", community: 3 },
    symbol("src/gymbook/booking.py", "Booking", 8, "class", 0),
    symbol("src/gymbook/booking.py", "book", 14, "function", 0),
    symbol("src/gymbook/booking.py", "cancel", 22, "function", 0),
    symbol("src/gymbook/models.py", "Member", 5, "class", 1),
    symbol("src/gymbook/models.py", "Slot", 11, "class", 1),
    symbol("src/gymbook/api.py", "create_booking", 16, "function", 0),
    symbol("tests/test_booking.py", "test_full_slot", 7, "function", 2),
  ],
  edges: [
    { source: "file:src/gymbook/api.py", target: "file:src/gymbook/booking.py", kind: "imports" },
    { source: "file:src/gymbook/api.py", target: "ext:fastapi", kind: "imports" },
    {
      source: "file:src/gymbook/booking.py",
      target: "file:src/gymbook/models.py",
      kind: "imports",
    },
    { source: "file:src/gymbook/booking.py", target: "ext:datetime", kind: "imports" },
    {
      source: "file:tests/test_booking.py",
      target: "file:src/gymbook/booking.py",
      kind: "imports",
    },
    { source: "mod:gymbook", target: "file:src/gymbook/api.py", kind: "defines" },
    { source: "mod:gymbook", target: "file:src/gymbook/booking.py", kind: "defines" },
    { source: "mod:gymbook", target: "file:src/gymbook/models.py", kind: "defines" },
    {
      source: "file:src/gymbook/booking.py",
      target: "sym:src/gymbook/booking.py:Booking",
      kind: "defines",
    },
    {
      source: "file:src/gymbook/booking.py",
      target: "sym:src/gymbook/booking.py:book",
      kind: "defines",
    },
    {
      source: "file:src/gymbook/booking.py",
      target: "sym:src/gymbook/booking.py:cancel",
      kind: "defines",
    },
    {
      source: "file:src/gymbook/models.py",
      target: "sym:src/gymbook/models.py:Member",
      kind: "defines",
    },
    {
      source: "file:src/gymbook/models.py",
      target: "sym:src/gymbook/models.py:Slot",
      kind: "defines",
    },
    {
      source: "sym:src/gymbook/api.py:create_booking",
      target: "sym:src/gymbook/booking.py:book",
      kind: "calls",
    },
    {
      source: "sym:src/gymbook/booking.py:book",
      target: "sym:src/gymbook/booking.py:Booking",
      kind: "calls",
    },
    {
      source: "sym:tests/test_booking.py:test_full_slot",
      target: "sym:src/gymbook/booking.py:book",
      kind: "tests",
    },
    {
      source: "sym:src/gymbook/booking.py:Booking",
      target: "sym:src/gymbook/models.py:Slot",
      kind: "inherits",
    },
  ],
};

export function graphArtifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: "a-graph",
    project: PROJECT_ID,
    kind: "code_graph",
    name: "code_graph.json",
    version: 1,
    content_hash: "h",
    phase_run: null,
    produced_by: { role: "architect", turn_id: null },
    created_at: "2026-11-14T10:01:00Z",
    content: "",
    data: codeGraphData,
    ...overrides,
  };
}
