import { describe, expect, test } from "vitest";

import { scanSceneCode } from "./denylist";

describe("scanSceneCode", () => {
  test("accepts benign scene code", () => {
    const code = "export default (ctx) => ({ draw(p) { p.background(255); ctx.ready(); } })";
    expect(scanSceneCode(code).ok).toBe(true);
  });

  test.each([
    ["fetch('https://x')", "fetch"],
    ["new XMLHttpRequest()", "XMLHttpRequest"],
    ["import('./x.js')", "dynamic import"],
    ["eval('1+1')", "eval"],
    ["new Function('return 1')", "Function"],
    ["document.cookie", "cookie"],
    ["localStorage.getItem('x')", "localStorage"],
    ["window.parent.location", "parent"],
    ["window.top.postMessage", "top"],
  ])("rejects %s", (code) => {
    const result = scanSceneCode(code);
    expect(result.ok).toBe(false);
    expect(result.reason).toBeTruthy();
  });
});
