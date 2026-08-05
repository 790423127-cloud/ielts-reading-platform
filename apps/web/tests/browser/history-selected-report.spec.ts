import { expect, test } from "@playwright/test";

const sessions = [
  {
    session_id: "session-a",
    test_id: "b5-test-a",
    test_title: "剑雅5 Test A",
    created_at: "2026-07-29T12:36:00+00:00",
    score: 22,
    total: 40,
    accuracy: 55,
    estimated_band: 4.5,
    exam_mode: "study",
    part_numbers: [1, 2, 3],
    archived: false
  },
  {
    session_id: "session-b",
    test_id: "b6-test-b",
    test_title: "剑雅6 Test B",
    created_at: "2026-08-02T08:00:00+00:00",
    score: 30,
    total: 40,
    accuracy: 75,
    estimated_band: 6,
    exam_mode: "study",
    part_numbers: [1, 2, 3],
    archived: false
  },
  {
    session_id: "session-c",
    test_id: "b7-test-a",
    test_title: "剑雅7 Test A",
    created_at: "2026-08-03T08:00:00+00:00",
    score: 40,
    total: 40,
    accuracy: 100,
    estimated_band: 9,
    exam_mode: "study",
    part_numbers: [1, 2, 3],
    archived: false
  }
];

test("勾选练习记录后只汇总所选记录并可下载PDF", async ({ page }) => {
  const reportRequests: Array<{ session_ids: string[]; title: string }> = [];
  await page.route("**/api/v1/sessions?**", (route) => route.fulfill({ json: sessions }));
  await page.route("**/api/v1/reports/selection*", async (route) => {
    const payload = route.request().postDataJSON() as { session_ids: string[]; title: string };
    reportRequests.push(payload);
    if (new URL(route.request().url()).pathname.endsWith(".pdf")) {
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: Buffer.from("%PDF-1.4 selected report")
      });
      return;
    }
    await route.fulfill({
      json: {
        report_type: "stage",
        engine_version: "test",
        generated_from: "persisted_sessions",
        ai_calls: 0,
        summary: {
          title: payload.title,
          session_count: 2,
          first_attempt_count: 2,
          retry_count: 0,
          correct: 52,
          total_questions: 80,
          accuracy: 65,
          total_elapsed_seconds: 7200,
          estimated_band: "6.0"
        },
        trend: [
          { session_id: "session-a", created_at: sessions[0].created_at, test_title: sessions[0].test_title, practice_mode: "full_test", score: 22, total: 40, accuracy: 55, elapsed_seconds: 3600, attempt_kind: "first", attempt_number: 1 },
          { session_id: "session-b", created_at: sessions[1].created_at, test_title: sessions[1].test_title, practice_mode: "full_test", score: 30, total: 40, accuracy: 75, elapsed_seconds: 3600, attempt_kind: "first", attempt_number: 1 }
        ],
        question_type_matrix: [],
        representative_questions: [],
        slowest_correct_questions: [],
        slowest_wrong_questions: [],
        deterministic_interpretation: [],
        data_notes: []
      }
    });
  });

  await page.goto("/history");
  await expect(page.locator(".history-table tbody tr")).toHaveCount(3);
  await page.locator(".history-table tbody tr").nth(0).locator('input[type="checkbox"]').check();
  await page.locator(".history-table tbody tr").nth(1).locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "生成汇总报告（2）" }).click();

  const dialog = page.getByRole("dialog", { name: "勾选汇总报告" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("2 次");
  await expect(dialog).toContainText("52/80");
  await expect(dialog).toContainText("65%");
  await expect(dialog).toContainText("剑雅5 Test A");
  await expect(dialog).toContainText("剑雅6 Test B");
  await expect(dialog).not.toContainText("剑雅7 Test A");
  expect(new Set(reportRequests[0].session_ids)).toEqual(new Set(["session-a", "session-b"]));

  const downloadPromise = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "下载汇总 PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("IELTS G类阅读勾选汇总报告（2次）.pdf");
  expect(new Set(reportRequests[1].session_ids)).toEqual(new Set(["session-a", "session-b"]));
});
