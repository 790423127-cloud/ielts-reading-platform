import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("../components/HistoryCenter.tsx", import.meta.url),
  "utf8"
);
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("history center supports row selection, visible select-all and permanent batch deletion", () => {
  assert.match(component, /selectedIds/);
  assert.match(component, /aria-label="选择全部当前记录"/);
  assert.match(component, /全选当前/);
  assert.match(component, /批量删除（\$\{selectedIds\.size\}）/);
  assert.match(component, /deleteSessions\(sessionIds\)/);
  assert.match(component, /删除后无法恢复/);
  assert.match(component, /current\.filter\(\(item\) => !deletedIds\.has\(item\.session_id\)\)/);
  assert.match(api, /\/api\/v1\/sessions\/delete-batch/);
});

test("each history row can be permanently deleted while legacy archived rows remain restorable", () => {
  assert.match(component, /onClick=\{\(\) => void remove\(item\)\}>永久删除/);
  assert.match(component, /onClick=\{\(\) => void restore\(item\)\}>恢复/);
  assert.match(component, /确定永久删除这条练习记录吗？删除后无法恢复/);
  assert.match(component, /deleteSession\(summary\.session_id\)/);
});
