import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("../components/HistoryCenter.tsx", import.meta.url),
  "utf8"
);
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const styles = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

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

test("selected history rows can generate and download one combined report", () => {
  assert.match(component, /生成汇总报告（\$\{selectedIds\.size\}）/);
  assert.match(component, /fetchSelectedStageReport\(sessionIds, title\)/);
  assert.match(component, /aria-label="勾选汇总报告"/);
  assert.match(component, /下载汇总 PDF/);
  assert.match(component, /下载汇总 DOCX/);
  assert.match(component, /报告只读取已勾选记录，不会修改、归档或删除原数据/);
  assert.match(api, /\/api\/v1\/reports\/selection/);
  assert.match(api, /downloadSelectedStageReport/);
});

test("history actions remain visible as cards on narrow screens", () => {
  assert.match(component, /data-label="操作"/);
  assert.match(component, /data-label="成绩"/);
  assert.match(styles, /\.history-table thead \{ display: none; \}/);
  assert.match(styles, /\.history-row-actions \{ display: grid; grid-template-columns: 1fr 1fr;/);
});

test("history translates internal practice mode codes for students", () => {
  assert.match(component, /function examModeLabel/);
  assert.match(component, /study: "学习模式"/);
  assert.match(component, /mock_exam: "完整模考"/);
  assert.match(component, /examModeLabel\(item\.exam_mode\)/);
});
