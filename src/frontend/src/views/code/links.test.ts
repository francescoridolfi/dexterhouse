// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { windowKey } from "../../os/apps.ts";
import { createWindowStore } from "../../os/windowStore.ts";
import { codeHref, graphHref, parseCodeSearch } from "./links.ts";
import { commands, repoDir, shellQuote } from "./location.ts";
import { codeLocation } from "../../test/codeFixtures.ts";

describe("Code deep links", () => {
  it("builds and parses ?path&line&ref", () => {
    const href = codeHref("p-1", { path: "src/a b.py", line: 12, ref: "abc123" });
    expect(href).toBe("/code/p-1?path=src%2Fa+b.py&line=12&ref=abc123");
    expect(parseCodeSearch(href.split("?")[1]!)).toEqual({
      path: "src/a b.py",
      line: 12,
      ref: "abc123",
    });
    expect(codeHref("p-1", { ref: "HEAD" })).toBe("/code/p-1");
    expect(graphHref("a-1")).toBe("/graph/a-1");
  });

  it("drops a bad line and defaults the ref", () => {
    expect(parseCodeSearch("?path=x.py&line=-3")).toEqual({
      path: "x.py",
      line: null,
      ref: "HEAD",
    });
    expect(parseCodeSearch("?line=1.5").line).toBeNull();
    expect(parseCodeSearch("").path).toBeNull();
  });
});

describe("one Code window per project", () => {
  it("keys windows by app and instance", () => {
    expect(windowKey("/code/p-1?path=a.py&line=3")).toBe("code:p-1");
    expect(windowKey("/code")).toBe("code");
    expect(windowKey("/graph/a-9")).toBe("graph:a-9");
    expect(windowKey("/projects/p-1/board")).toBe("project");
    expect(windowKey("/")).toBeNull();
  });

  it("opens a window per project and keeps the deep link in its path", () => {
    const store = createWindowStore("/code/p-1?path=a.py&line=3");
    store.getState().visit("/code/p-2");
    store.getState().visit("/code/p-1?path=b.py");
    const { windows, order, focused } = store.getState();
    expect(order).toEqual(["code:p-2", "code:p-1"]);
    expect(focused).toBe("code:p-1");
    expect(windows["code:p-1"]?.path).toBe("/code/p-1?path=b.py");
    expect(windows["code:p-2"]?.rect).not.toEqual(windows["code:p-1"]?.rect);
    expect(store.getState().latest("code")?.id).toBe("code:p-1");
  });

  it("closes the project picker when a project is opened", () => {
    const store = createWindowStore("/code");
    expect(store.getState().windows.code?.transient).toBe(true);
    store.getState().visit("/code/p-1");
    expect(Object.keys(store.getState().windows)).toEqual(["code:p-1"]);
  });
});

describe("location commands", () => {
  it("clones and checks out the release branch, quoted", () => {
    const [checkout, copyOut] = commands(codeLocation);
    expect(checkout?.command).toBe(
      "git clone https://github.com/acme/gymbook.git && cd gymbook && git checkout dexterhouse/release-1",
    );
    expect(copyOut?.command).toBe("docker cp c0ffee12:/workspace ./workspace");
    expect(shellQuote("a b'c")).toBe("'a b'\\''c'");
    expect(repoDir("https://host/x/repo.git/")).toBe("repo");
  });

  it("only clones when nothing was delivered", () => {
    const ids = commands({ ...codeLocation, releases: [], workspace: null }).map((c) => c.id);
    expect(ids).toEqual(["clone"]);
  });
});
