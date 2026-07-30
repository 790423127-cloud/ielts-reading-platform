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
  assert.doesNotMatch(component, /详细版|导出历史|旧导出记录|内容版本/);
});

test("cross-article vocabulary recurrence shows one compact memory reminder", () => {
  assert.match(component, /function articleCount/);
  assert.match(component, /source\.source_type !== "reading_text"/);
  assert.match(component, /distinctArticles >= 2/);
  assert.match(component, /高频复现 · \{distinctArticles\} 篇文章，建议优先记忆/);
});
