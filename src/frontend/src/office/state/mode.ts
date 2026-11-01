// SPDX-License-Identifier: AGPL-3.0-or-later
// Visual state of an avatar at time `now` (ux_3d_office.md, table "Stati e animazioni").
import type { AvatarMode, AvatarModel, ToolIcon } from "./model.ts";

export function avatarMode(avatar: AvatarModel, now: number): AvatarMode {
  if (avatar.leaving) return "leaving";
  if (avatar.walking) return avatar.errand ? "handoff" : "walking";
  if (avatar.failedUntil > now) return "failed";
  if (avatar.blockedBy) return "blocked";
  if (avatar.celebrateUntil > now) return "celebrate";
  if (avatar.working) return "working";
  return "idle";
}

export const TOOL_EMOJI: Record<ToolIcon, string> = {
  read: "📄",
  write: "✏️",
  exec: "▶",
  tests: "🧪",
  marketplace: "🌐",
  other: "⚙",
};

export const MODE_EMOJI: Partial<Record<AvatarMode, string>> = {
  blocked: "⏳",
  failed: "❌",
  celebrate: "🎉",
};

/** 📄 read, ✏️ write, ▶ exec, 🧪 tests, 🌐 marketplace (MCP tool names, e.g. `fs.read_file`). */
export function toolIcon(tool: string): ToolIcon {
  const name = tool.toLowerCase();
  if (/test/.test(name)) return "tests";
  if (/marketplace|registry|package|recruit/.test(name)) return "marketplace";
  if (/exec|run|shell|command|git/.test(name)) return "exec";
  if (/write|edit|create|update|patch|save|delete|commit/.test(name)) return "write";
  if (/read|get|list|search|find|load|fetch|view/.test(name)) return "read";
  return "other";
}
