import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const shell = fs.readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");

test("Next.js owns navigation instead of legacy hash routers", () => {
  assert.match(shell, /usePathname/);
  assert.match(shell, /next\/link/);
  assert.doesNotMatch(layout + shell, /hashchange|popstate|MutationObserver|V311Router|v320-nav-guard/);
});
