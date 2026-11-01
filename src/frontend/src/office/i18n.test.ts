// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { officeStrings } from "./i18n.ts";

function keys(value: object, prefix = ""): string[] {
  return Object.entries(value).flatMap(([key, child]) =>
    typeof child === "object" && child !== null
      ? keys(child as object, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

describe("office strings", () => {
  it("have the same keys in English and Italian", () => {
    expect(keys(officeStrings.it).sort()).toEqual(keys(officeStrings.en).sort());
  });
});
