export type HealthResponse = {
  ok: boolean;
  service: string;
  version: string;
  migrationPhase: string;
  databaseConnected: boolean;
  features: Record<string, boolean>;
};

export type TestIndexItem = {
  id: string;
  book: string;
  book_number: number;
  name: string;
  title: string;
  part_count: number;
  question_count: number;
};

export type QuestionOption = { code: string; text: string };
export type PassageParagraph = {
  label?: string;
  index?: number;
  text: string;
  translation?: string;
};
export type PublicQuestion = {
  id: string;
  number: number;
  display_number?: number | string;
  prompt: string;
  options?: unknown[];
};
export type PublicQuestionGroup = {
  id?: string;
  instructions?: string;
  question_type: string;
  question_subtype: string;
  question_category?: string;
  question_label?: string;
  normalized_options?: QuestionOption[];
  shared_options?: unknown[];
  options?: unknown[];
  required_choices?: number;
  questions: PublicQuestion[];
};
export type PublicPart = {
  id?: string;
  number: number;
  title: string;
  article_title?: string;
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
  number: number | string;
  part_number: number;
  question_type: string;
  question_subtype: string;
  prompt: string;
  user_answer: string;
  correct_answer: string;
  is_correct: boolean;
  answer_error_type?: string | null;
  analysis?: string;
  reason?: string;
  paraphrasing?: string;
  evidence?: string[];
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
  part_results: Array<{ part_number: number; title: string; score: number; total: number; accuracy: number }>;
  question_results: QuestionResult[];
  wrong_questions: QuestionResult[];
  unanswered_count: number;
  estimated_gt_reading_band?: number;
  band_estimate: BandEstimate;
  timed_out?: boolean;
};
export type SessionEnvelope = {
  session_id: string;
  created_at: string;
  idempotent_replay: boolean;
  result: ScoringResult;
};
export type SessionSummary = {
  session_id: string;
  test_id: string;
  test_title: string;
  created_at: string;
  score: number;
  total: number;
  accuracy: number;
  estimated_band?: number | null;
  exam_mode: string;
  part_numbers: number[];
};
export type SubmitSessionPayload = {
  user_id?: string;
  test_id: string;
  client_submission_id: string;
  answers: Record<string, string | string[]>;
  elapsed_seconds: number;
  exam_mode: "study" | "part_practice" | "mock_exam";
  part_numbers: number[];
  timed_out?: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

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

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiJson<HealthResponse>("/api/v1/health", { signal });
}

export async function fetchTests(signal?: AbortSignal): Promise<TestIndexItem[]> {
  const data = await apiJson<{ items: TestIndexItem[] }>("/api/v1/question-bank/tests", { signal });
  return data.items;
}

export async function fetchPublicTest(testId: string, signal?: AbortSignal): Promise<PublicTest> {
  return apiJson<PublicTest>(`/api/v1/question-bank/tests/${encodeURIComponent(testId)}`, { signal });
}

export async function submitSession(payload: SubmitSessionPayload): Promise<SessionEnvelope> {
  return apiJson<SessionEnvelope>("/api/v1/sessions/submit", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchSessions(userId = "owner", signal?: AbortSignal): Promise<SessionSummary[]> {
  return apiJson<SessionSummary[]>(`/api/v1/sessions?user_id=${encodeURIComponent(userId)}`, { signal });
}

export async function fetchSession(sessionId: string, userId = "owner", signal?: AbortSignal): Promise<SessionEnvelope> {
  return apiJson<SessionEnvelope>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(userId)}`,
    { signal }
  );
}
