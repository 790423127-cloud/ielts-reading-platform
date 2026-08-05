import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("../components/VocabularyCenter.tsx", import.meta.url),
  "utf8"
);
const api = readFileSync(new URL("../lib/learningApi.ts", import.meta.url), "utf8");

test("vocabulary center keeps export controls limited to unexported and selected words", () => {
  assert.match(component, /导出未导出/);
  assert.match(component, /导出已选/);
  assert.match(component, /only_unexported: onlyUnexported/);
  assert.match(component, /type="checkbox"/);
  assert.match(api, /item_ids: string\[\]/);
  assert.match(api, /only_unexported: boolean/);
  assert.doesNotMatch(component, /详细版|导出历史|内容版本/);
});

test("cross-article vocabulary recurrence shows one compact memory reminder", () => {
  assert.match(component, /function articleCount/);
  assert.match(component, /source\.source_type !== "reading_text"/);
  assert.match(component, /distinctArticles >= 2/);
  assert.match(component, /高频复现 · \{distinctArticles\} 篇文章，建议优先记忆/);
});

test("manual duplicate captures keep their own frequency and high-frequency reminder", () => {
  assert.match(api, /manual_capture_count: number/);
  assert.match(component, /item\.manual_capture_count >= 2/);
  assert.match(component, /手动高频 · 已记录 \{item\.manual_capture_count\} 次/);
  assert.match(component, /手动记录 \$\{item\.manual_capture_count\} 次/);
  assert.match(component, /手动重复保存会累计频率/);
});

test("wrong-question paraphrase tab exports a portable learning package", () => {
  assert.match(component, /错题同义替换/);
  assert.match(component, /exportParaphraseSelection/);
  assert.match(component, /交卷后系统只读取错题/);
  assert.match(api, /\/api\/v1\/vocabulary\/paraphrases\/export/);
  assert.match(api, /ielts-paraphrases-selected\.json/);
  assert.match(component, /format: "json"/);
  assert.match(component, /原文证据/);
});

test("vocabulary search exposes an accessible name in both tabs", () => {
  assert.match(component, /aria-label=\{activeTab === "words" \? "搜索生词" : "搜索同义替换"\}/);
});
