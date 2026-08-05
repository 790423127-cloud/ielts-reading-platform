import {
  cacheSessionAnnotations,
  readAnnotationsForSubmission,
  rememberCurrentReadingTest,
  type ReadingAnnotation
} from "@/lib/readingAnnotations";
import type {
  ApiSessionEnvelope,
  ApiSessionSubmitRequest,
  HealthResponse as ContractHealthResponse,
  SessionSummary as ContractSessionSummary
} from "@ielts-reading/contracts";

export type HealthResponse = ContractHealthResponse;

export type QuestionBankMigrationStatus = {
  expected_tests: number;
  found_tests: number;
  expected_questions: number;
  found_questions: number;
  ready: boolean;
  baseline_expected_tests: number;
  baseline_ready: boolean;
  missing_test_ids: string[];
  missing_baseline_test_ids: string[];
};

export type TestIndexItem = {
  id: string;
  book: string;
  book_number: number;
  name: string;
  title: string;
  part_count: number;
  question_count: number;
  difficulty: DifficultyRating;
  part_difficulties: Array<DifficultyRating & { part_number: number }>;
};

export type DifficultyRating = {
  level: "easy" | "medium" | "hard";
  label: string;
  caption: string;
  description: string;
  score: number;
  relative_percentile: number;
  official: false;
};

export type QuestionOption = { code: string; text: string };
export type PassageParagraph = {
  label?: string;
  index?: number;
  text: string;
  translation?: string;
  table?: {
    caption?: string;
    intro?: string;
    headers: string[];
    rows: string[][];
    notes?: string[];
  };
  question_cue?: {
    start: number;
    end: number;
  };
};
export type PublicQuestion = {
  id: string;
  number: number;
  display_number?: number | string;
  prompt: string;
  options?: unknown[];
};
export type SourceQuestionOption = {
  index?: string;
  content_html?: string;
};
export type SourceStructuredQuestion = {
  content_html?: string;
  options?: SourceQuestionOption[];
};
export type SourceQuestionGroup = {
  position: number;
  navigation?: string;
  display_start?: number | null;
  display_end?: number | null;
  start_index?: number;
  end_index?: number;
  question_type: number;
  interaction_mode?: "text_entry" | "single_choice" | "multiple_choice" | "judgement" | "matching_matrix";
  required_choices?: number | null;
  instructions_html?: string;
  questions_html?: string;
  structured_questions?: SourceStructuredQuestion[];
  match_options?: SourceQuestionOption[];
  options_title?: string;
};
export type PublicQuestionGroup = {
  id?: string;
  instructions?: string;
  source_question_groups?: SourceQuestionGroup[];
  question_type: string;
  question_subtype: string;
  question_category?: string;
  question_label?: string;
  normalized_options?: QuestionOption[];
  shared_options?: unknown[];
  options?: unknown[];
  required_choices?: number;
  shared_response?: boolean;
  shared_response_question_ids?: string[];
  shared_response_numbers?: number[];
  content_template?: string;
  image_url?: string;
  table?: {
    title?: string;
    rows?: string[][];
    content?: string[][];
  } | null;
  questions: PublicQuestion[];
};
export type PublicPart = {
  id?: string;
  number: number;
  title: string;
  source_html?: string;
  source_visual_name?: string;
  article_title?: string;
  source_article_title?: string;
  subtitle?: string;
  paragraphs?: PassageParagraph[];
  groups: PublicQuestionGroup[];
};
export type PublicTest = {
  id: string;
  title: string;
  book?: string;
  name?: string;
  parts: PublicPart[];
};

export type BandEstimate = {
  eligible: boolean;
  raw_score: number;
  out_of: number;
  estimated_band?: number | null;
  display_band?: string | null;
  next_band?: number | null;
  questions_to_next_band?: number | null;
  notice_zh?: string | null;
};
export type QuestionResult = {
  id: string;
  source_question_id?: string;
  number: number | string;
  part_number: number;
  part_title?: string;
  source_part_number?: number;
  source_test_id?: string;
  question_type: string;
  question_subtype: string;
  question_category?: string;
  prompt: string;
  instructions?: string;
  options?: unknown[];
  user_answer: string;
  correct_answer: string;
  is_correct: boolean;
  answer_error_type?: string | null;
  analysis?: string;
  reason?: string;
  location_analysis?: string;
  paraphrasing?: string;
  keywords?: string;
  evidence?: string[];
  evidence_available?: boolean;
  wrong_reasons?: unknown;
  elapsed_seconds?: number;
  shared_response?: boolean;
  shared_response_score?: number;
  shared_response_total?: number;
  credited_answer?: string;
  selected_correct_answers?: string[];
  selected_incorrect_answers?: string[];
  missed_correct_answers?: string[];
};
export type ScoringResult = {
  test_id: string;
  test_title: string;
  score: number;
  total: number;
  accuracy: number;
  total_elapsed_seconds: number;
  exam_mode: string;
  part_numbers: number[];
  part_results: Array<{ part_number: number; title: string; score: number; total: number; accuracy: number; elapsed_seconds: number }>;
  type_results?: Array<{ type: string; correct: number; total: number; accuracy: number }>;
  question_results: QuestionResult[];
  wrong_questions: QuestionResult[];
  unanswered_count: number;
  estimated_gt_reading_band?: number;
  band_estimate: BandEstimate;
  timed_out?: boolean;
  skill_id?: string;
  skill_label?: string;
  source_question_refs?: string[];
  source_policy?: string;
  annotations?: ReadingAnnotation[];
  ai_paraphrase_summary?: {
    status: "completed" | "skipped" | "failed";
    reason?: string;
    wrong_question_count: number;
    candidate_count: number;
    saved_count: number;
    skipped_count?: number;
    saved_ids?: string[];
    message?: string;
  };
};
export type SessionEnvelope = Omit<ApiSessionEnvelope, "result"> & {
  result: ScoringResult;
};
export type SessionSummary = ContractSessionSummary;
export type SubmitSessionPayload = Omit<
  ApiSessionSubmitRequest,
  "annotations" | "answers" | "partElapsedSeconds" | "questionElapsedSeconds" | "part_numbers"
> & {
  answers: Record<string, string | string[]>;
  partElapsedSeconds: Record<string, number>;
  questionElapsedSeconds: Record<string, number>;
  part_numbers: number[];
  annotations?: ReadingAnnotation[];
};

export type WrongReviewItem = QuestionResult & {
  source_session_id: string;
  source_test_id: string;
  source_part_number: number;
  source_question_id: string;
  source_question_ref: string;
  attempted_at: string;
  wrong_count: number;
  correct_streak_after_wrong: number;
  latest_result: "correct" | "wrong";
  last_attempt_at: string;
  method_course_id: string;
  recommended_skill_id: string;
  recommended_skill_label: string;
  mastery_rule: string;
  student_feedback?: {
    session_id: string;
    question_id: string;
    match_status: "matches" | "partial" | "does_not_match";
    understanding_status: "understood" | "needs_review";
    cause_id?: string | null;
    note: string;
    updated_at: string;
  } | null;
};

export type MethodCourse = {
  id: string;
  kind: "foundation" | "subtype";
  subtype?: string;
  title: string;
  objective: string;
  steps?: string[];
  traps?: string[];
  checklist?: string[];
  family?: string;
  family_label?: string;
  summary?: string;
  first_move?: string;
  suggested_minutes?: number;
  section_count?: number;
  recognition?: string[];
  opening?: {
    look: string;
    mark: string;
    say: string;
    avoid: string;
    critical_words: string[];
  };
  child_guide?: {
    plain_language: string;
    goal: string;
    memory_sentence: string;
    before_you_start: string[];
  };
  difficulty_ladder?: Array<{ level: string; signal: string; action: string; course_tip?: string; warning_signals?: string[] }>;
  foundation_guide?: {
    title: string;
    intro: string;
    answer_form: string;
    rules: Array<{ signal: string; meaning: string; action: string; example: string }>;
  };
  decision_guide?: Array<{ signal: string; meaning: string; action: string; example?: string }>;
  vocabulary_guide?: {
    must_understand: string[];
    can_delay: string[];
    fallback: string;
    steps: Array<{ title: string; action: string; example?: string }>;
    critical_words: string[];
  };
  long_sentence_guide?: Array<{ title: string; action: string; example?: string }>;
  mini_example?: { context: string; question: string; answer: string; reasoning: string[] };
  standard_method?: Array<{ id?: string; title: string; action: string; why?: string; example?: string }>;
  special_rules?: string[];
  hard_rescue?: string[];
  time_plan?: { easy: string; normal: string; hard: string };
  offline_policy?: string;
};

export type AbilitySkill = {
  id: string;
  label: string;
  objective: string;
  subtype_ids: string[];
  source_policy: string;
  available_questions: number;
  question_subtype?: string;
};
export type AbilityQuestionItem = {
  ref_id: string;
  test_id: string;
  test_title: string;
  part_number: number;
  original_question_id: string;
  skill_id: string;
  passage: {
    part_number: number;
    title: string;
    article_title: string;
    subtitle: string;
    paragraphs: PassageParagraph[];
  };
  group: PublicQuestionGroup;
};
export type AbilitySet = {
  id: string;
  skill: Omit<AbilitySkill, "available_questions" | "source_policy">;
  items: AbilityQuestionItem[];
  total_available: number;
  next_cursor: number;
  source_policy: "verified_question_bank_only";
  training_kind?: "ability" | "question_type" | "wrong_batch";
  exact_question_replay?: boolean;
};
export type AbilitySubmitPayload = {
  user_id?: string;
  client_submission_id: string;
  skill_id: string;
  question_refs: string[];
  answers: Record<string, string | string[]>;
  elapsed_seconds: number;
  question_elapsed_seconds: Record<string, number>;
};

export type TimedQuestionReportItem = {
  source_question_ref: string;
  test_title: string;
  question_number: number | string;
  question_type: string;
  question_subtype: string;
  prompt: string;
  user_answer: string;
  correct_answer: string;
  elapsed_seconds: number;
  is_correct: boolean;
  created_at: string;
};

export type TrainingCatalog = {
  skills: AbilitySkill[];
  questionTypes: AbilitySkill[];
};

export type StageReport = {
  report_type: "stage" | "teacher_assignment";
  engine_version: string;
  layout_type?: string;
  layout_label?: string;
  generated_from: "persisted_sessions";
  ai_calls: number;
  summary: {
    title?: string;
    session_count: number;
    first_attempt_count: number;
    retry_count: number;
    correct: number;
    total_questions: number;
    wrong?: number;
    unanswered?: number;
    accuracy: number;
    total_elapsed_seconds: number;
    date_from?: string | null;
    date_to?: string | null;
    estimated_band?: string | null;
  };
  tfng_confusion_stats?: {
    false_vs_not_given: number;
    true_vs_not_given: number;
    true_vs_false: number;
    other: number;
    total_tfng_wrong: number;
  };
  time_management_notes?: string[];
  trend: Array<{
    session_id: string;
    created_at: string;
    test_title: string;
    practice_mode: string;
    skill_label?: string | null;
    score: number;
    total: number;
    accuracy: number;
    elapsed_seconds: number;
    attempt_kind: "first" | "retry";
    attempt_number: number;
  }>;
  question_type_matrix: Array<{
    question_subtype: string;
    question_type: string;
    correct: number;
    total: number;
    accuracy: number;
    status: string;
    status_label: string;
    sample_level: string;
  }>;
  part_results?: Array<{
    title: string;
    correct: number;
    total: number;
    accuracy: number;
    status_label: string;
    sample_level: string;
  }>;
  error_cause_distribution?: Array<{
    label: string;
    count: number;
    session_count: number;
    examples: string[];
  }>;
  teacher_observation_points?: string[];
  representative_questions: Array<{
    source_question_ref: string;
    test_title: string;
    question_number: number | string;
    question_type: string;
    question_subtype: string;
    prompt: string;
    user_answer: string;
    correct_answer: string;
    analysis: string;
    evidence: string[];
    source?: string;
    source_part_number?: number;
    cause_label?: string;
    student_confirmation_label?: string;
    teacher_observation?: string;
    location_analysis?: string;
    elapsed_seconds?: number;
    created_at: string;
  }>;
  slowest_correct_questions: TimedQuestionReportItem[];
  slowest_wrong_questions: TimedQuestionReportItem[];
  deterministic_interpretation: string[];
  data_notes: string[];
  selected_session_ids?: string[];
};

export type AiProviderStatus = {
  selected: string;
  selected_label: string;
  configured: boolean;
  model: string;
  providers: Array<{
    id: string;
    label: string;
    configured: boolean;
    model: string;
    base_url?: string | null;
  }>;
};

export type TeacherAssignmentModule = {
  id: string;
  title: string;
  module_type: "full_test" | "part" | "question_type" | "review" | "mixed";
  target_count: number;
  sort_order: number;
  session_ids: string[];
};

export type TeacherAssignment = {
  id: string;
  title: string;
  description: string;
  due_at?: string | null;
  status: "active" | "completed" | "archived";
  session_ids: string[];
  modules: TeacherAssignmentModule[];
  created_at: string;
  updated_at: string;
};

export type TeacherReportSnapshot = {
  id: string;
  assignment_id: string;
  title: string;
  created_at: string;
  report: StageReport & { assignment?: TeacherAssignment };
};

export type DurableAiJobItem = {
  id: string;
  question_id: string;
  question_number?: number | null;
  status: "pending" | "in_progress" | "completed" | "failed";
  attempt_count: number;
  error_message?: string | null;
  result?: {
    answer?: string;
    cached?: boolean;
    provider?: string | null;
    model?: string | null;
    conversation_id?: string | null;
  } | null;
  updated_at: string;
};

export type DurableAiJob = {
  id: string;
  session_id: string;
  idempotency_key: string;
  status: "pending" | "running" | "partial" | "completed" | "failed";
  provider: string;
  model: string;
  total_items: number;
  completed_items: number;
  failed_items: number;
  created_at: string;
  updated_at: string;
  items: DurableAiJobItem[];
  policy: {
    creation_calls_ai: false;
    resume_processes_at_most: number;
    max_attempts_per_item: number;
    automatic_paid_provider_fallback: false;
  };
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8010";

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  const data = await response.json().catch(() => null) as unknown;
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data
      ? (data as { detail?: unknown }).detail
      : data;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message?: unknown }).message)
        : `请求失败（${response.status}）`;
    throw new Error(message);
  }
  return data as T;
}

function cacheEnvelopeAnnotations(envelope: SessionEnvelope): SessionEnvelope {
  const annotations = envelope.result.annotations || [];
  cacheSessionAnnotations({
    sessionId: envelope.session_id,
    testId: envelope.result.test_id,
    testTitle: envelope.result.test_title,
    annotations
  });
  return envelope;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiJson<HealthResponse>("/api/v1/health", { signal });
}

export async function fetchTests(signal?: AbortSignal): Promise<TestIndexItem[]> {
  const data = await apiJson<{ items: TestIndexItem[] }>("/api/v1/question-bank/tests", { signal });
  return data.items;
}

export async function fetchQuestionBankStatus(signal?: AbortSignal): Promise<QuestionBankMigrationStatus> {
  return apiJson<QuestionBankMigrationStatus>("/api/v1/question-bank/migration-status", { signal });
}

export async function fetchPublicTest(testId: string, signal?: AbortSignal): Promise<PublicTest> {
  const test = await apiJson<PublicTest>(`/api/v1/question-bank/tests/${encodeURIComponent(testId)}`, { signal });
  rememberCurrentReadingTest({ id: test.id, title: test.title });
  return test;
}

export async function submitSession(payload: SubmitSessionPayload): Promise<SessionEnvelope> {
  const annotations = payload.annotations || readAnnotationsForSubmission(payload.test_id, payload.part_numbers);
  const envelope = await apiJson<SessionEnvelope>("/api/v1/sessions/submit", {
    method: "POST",
    body: JSON.stringify({ ...payload, annotations })
  });
  return cacheEnvelopeAnnotations(envelope);
}

export async function fetchSessions(userId = "owner", signal?: AbortSignal, includeArchived = false): Promise<SessionSummary[]> {
  return apiJson<SessionSummary[]>(`/api/v1/sessions?user_id=${encodeURIComponent(userId)}&limit=100&include_archived=${includeArchived}`, { signal });
}

export async function fetchSession(sessionId: string, userId = "owner", signal?: AbortSignal): Promise<SessionEnvelope> {
  const envelope = await apiJson<SessionEnvelope>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(userId)}`,
    { signal }
  );
  return cacheEnvelopeAnnotations(envelope);
}

export async function fetchWrongQuestions(userId = "owner", signal?: AbortSignal): Promise<WrongReviewItem[]> {
  const data = await apiJson<{ items: WrongReviewItem[] }>(
    `/api/v1/review/wrong-questions?user_id=${encodeURIComponent(userId)}&limit=500`,
    { signal }
  );
  return data.items;
}

export async function fetchMethodCourses(signal?: AbortSignal): Promise<MethodCourse[]> {
  const data = await apiJson<{ items: MethodCourse[] }>("/api/v1/methods", { signal });
  return data.items;
}

export async function saveWrongQuestionFeedback(
  item: WrongReviewItem,
  feedback: {
    match_status: "matches" | "partial" | "does_not_match";
    understanding_status: "understood" | "needs_review";
    cause_id?: string | null;
    note?: string;
  }
): Promise<NonNullable<WrongReviewItem["student_feedback"]>> {
  return apiJson<NonNullable<WrongReviewItem["student_feedback"]>>(
    `/api/v1/review/wrong-questions/${encodeURIComponent(item.source_session_id)}/${encodeURIComponent(item.id)}/feedback`,
    {
      method: "POST",
      body: JSON.stringify({ user_id: "owner", ...feedback })
    }
  );
}

export async function fetchDurableAiJobs(signal?: AbortSignal): Promise<DurableAiJob[]> {
  const data = await apiJson<{ items: DurableAiJob[] }>(
    "/api/v1/ai-jobs?user_id=owner&limit=50",
    { signal }
  );
  return data.items;
}

export async function createDurableAiJob(payload: {
  session_id: string;
  question_ids: string[];
  idempotency_key: string;
}): Promise<DurableAiJob> {
  return apiJson<DurableAiJob>("/api/v1/ai-jobs", {
    method: "POST",
    body: JSON.stringify({ user_id: "owner", ...payload })
  });
}

export async function resumeDurableAiJob(jobId: string): Promise<DurableAiJob> {
  return apiJson<DurableAiJob>(`/api/v1/ai-jobs/${encodeURIComponent(jobId)}/resume`, {
    method: "POST",
    body: JSON.stringify({ user_id: "owner" })
  });
}

export async function fetchMethodCourse(courseId: string, signal?: AbortSignal): Promise<MethodCourse> {
  return apiJson<MethodCourse>(`/api/v1/methods/${encodeURIComponent(courseId)}`, { signal });
}

export async function fetchTrainingCatalog(signal?: AbortSignal): Promise<TrainingCatalog> {
  const data = await apiJson<{ items: AbilitySkill[]; question_types: AbilitySkill[] }>(
    "/api/v1/ability/skills",
    { signal }
  );
  return { skills: data.items, questionTypes: data.question_types };
}

export async function generateAbilitySet(
  skillId: string,
  count = 8,
  cursor = 0,
  questionRefs: string[] = []
): Promise<AbilitySet> {
  return apiJson<AbilitySet>("/api/v1/ability/generate", {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId, count, cursor, question_refs: questionRefs })
  });
}

export async function submitAbilitySet(payload: AbilitySubmitPayload): Promise<SessionEnvelope> {
  return apiJson<SessionEnvelope>("/api/v1/ability/submit", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchStageReport(userId = "owner", signal?: AbortSignal): Promise<StageReport> {
  return apiJson<StageReport>(
    `/api/v1/reports/stage?user_id=${encodeURIComponent(userId)}&limit=500`,
    { signal }
  );
}

export function stageReportDownloadUrl(
  extension: "pdf" | "docx",
  userId = "owner"
): string {
  return `${API_BASE_URL}/api/v1/reports/stage.${extension}?user_id=${encodeURIComponent(userId)}&limit=500`;
}

export async function fetchSelectedStageReport(
  sessionIds: string[],
  title: string,
  userId = "owner"
): Promise<StageReport> {
  return apiJson<StageReport>("/api/v1/reports/selection", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, session_ids: sessionIds, title })
  });
}

export async function downloadSelectedStageReport(
  sessionIds: string[],
  title: string,
  extension: "pdf" | "docx",
  userId = "owner"
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/v1/reports/selection.${extension}`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, session_ids: sessionIds, title })
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = data?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message?: unknown }).message)
        : `汇总报告下载失败（${response.status}）`;
    throw new Error(message);
  }
  return response.blob();
}

export function sessionReportDownloadUrl(
  sessionId: string,
  extension: "pdf" | "docx",
  userId = "owner"
): string {
  return `${API_BASE_URL}/api/v1/reports/sessions/${encodeURIComponent(sessionId)}.${extension}?user_id=${encodeURIComponent(userId)}`;
}

export async function deleteSession(sessionId: string, userId = "owner"): Promise<void> {
  await apiJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(userId)}`, {
    method: "DELETE"
  });
}

export async function deleteSessions(
  sessionIds: string[],
  userId = "owner"
): Promise<{
  deleted_count: number;
  deleted_ids: string[];
  missing_ids: string[];
  recoverable: false;
}> {
  return apiJson("/api/v1/sessions/delete-batch", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, session_ids: sessionIds })
  });
}

export async function restoreSession(sessionId: string, userId = "owner"): Promise<void> {
  await apiJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}/restore?user_id=${encodeURIComponent(userId)}`, {
    method: "POST"
  });
}

export async function fetchAiProviderStatus(signal?: AbortSignal): Promise<AiProviderStatus> {
  return apiJson<AiProviderStatus>("/api/v1/ai-teacher/provider", { signal });
}

export async function selectAiProvider(provider: string): Promise<AiProviderStatus> {
  return apiJson<AiProviderStatus>("/api/v1/ai-teacher/provider", {
    method: "PUT",
    body: JSON.stringify({ provider })
  });
}

export async function fetchTeacherAssignments(userId = "owner", signal?: AbortSignal): Promise<TeacherAssignment[]> {
  const data = await apiJson<{ items: TeacherAssignment[] }>(
    `/api/v1/teacher/assignments?user_id=${encodeURIComponent(userId)}`,
    { signal }
  );
  return data.items;
}

export async function createTeacherAssignment(payload: {
  user_id?: string;
  title: string;
  description?: string;
  due_at?: string | null;
}): Promise<TeacherAssignment> {
  return apiJson<TeacherAssignment>("/api/v1/teacher/assignments", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateTeacherAssignment(assignment: TeacherAssignment): Promise<TeacherAssignment> {
  return apiJson<TeacherAssignment>(`/api/v1/teacher/assignments/${encodeURIComponent(assignment.id)}`, {
    method: "PUT",
    body: JSON.stringify({
      user_id: "owner",
      title: assignment.title,
      description: assignment.description,
      due_at: assignment.due_at,
      status: assignment.status,
      session_ids: assignment.session_ids,
      modules: assignment.modules.map((module) => ({
        id: module.id,
        title: module.title,
        module_type: module.module_type,
        target_count: module.target_count,
        session_ids: module.session_ids
      }))
    })
  });
}

export async function fetchTeacherReport(assignmentId: string, signal?: AbortSignal): Promise<StageReport> {
  return apiJson<StageReport>(
    `/api/v1/teacher/assignments/${encodeURIComponent(assignmentId)}/report?user_id=owner`,
    { signal }
  );
}

export async function createTeacherReportSnapshot(assignmentId: string): Promise<TeacherReportSnapshot> {
  return apiJson<TeacherReportSnapshot>(
    `/api/v1/teacher/assignments/${encodeURIComponent(assignmentId)}/snapshots?user_id=owner`,
    { method: "POST" }
  );
}

export async function fetchTeacherReportSnapshots(signal?: AbortSignal): Promise<TeacherReportSnapshot[]> {
  const data = await apiJson<{ items: TeacherReportSnapshot[] }>(
    "/api/v1/teacher/report-snapshots?user_id=owner",
    { signal }
  );
  return data.items;
}

export function teacherReportDownloadUrl(
  source: { assignmentId: string } | { snapshotId: string },
  extension: "pdf" | "docx"
): string {
  const path = "assignmentId" in source
    ? `/api/v1/teacher/assignments/${encodeURIComponent(source.assignmentId)}/report.${extension}`
    : `/api/v1/teacher/report-snapshots/${encodeURIComponent(source.snapshotId)}.${extension}`;
  return `${API_BASE_URL}${path}?user_id=owner`;
}
