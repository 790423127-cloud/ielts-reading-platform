import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const stage = readFileSync(new URL("../components/StageReportCenter.tsx", import.meta.url), "utf8");
const history = readFileSync(new URL("../components/HistoryCenter.tsx", import.meta.url), "utf8");
const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");

test("stage and single-session reports expose formal PDF and DOCX downloads", () => {
  assert.match(api, /stageReportDownloadUrl/);
  assert.match(api, /sessionReportDownloadUrl/);
  assert.match(api, /\/api\/v1\/reports\/stage\.\$\{extension\}/);
  assert.match(api, /\/api\/v1\/reports\/sessions\/\$\{encodeURIComponent\(sessionId\)\}\.\$\{extension\}/);
  assert.match(stage, /下载正式 PDF/);
  assert.match(stage, /下载 DOCX/);
  assert.match(history, /sessionReportDownloadUrl\(detail\.summary\.session_id, "pdf"\)/);
  assert.match(history, /sessionReportDownloadUrl\(detail\.summary\.session_id, "docx"\)/);
  assert.match(workbench, /sessionReportDownloadUrl\(resultSessionId, "pdf"\)/);
  assert.match(workbench, /sessionReportDownloadUrl\(resultSessionId, "docx"\)/);
});
