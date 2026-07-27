export type LearningTask = {
  id: string;
  skill_key: string;
  skill_label: string;
  question_subtype?: string | null;
  reason_code?: string | null;
  source_session_id?: string | null;
  source_question_id?: string | null;
  source_wrong_at: string;
  recommended_course_id?: string | null;
  minimum_questions: number;
  target_accuracy: number;
  required_success_days: number;
  wrong_count: number;
  status: "not_started" | "learning" | "pending_validation" | "pending_review" | "mastered" | "retrain";
  status_label: string;
  current_question_count: number;
  recent_accuracy: number;
  success_streak: number;
  distinct_success_days: number;
  next_review_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SkillMastery = {
  skill_key: string;
  skill_label: string;
  attempts: number;
  correct: number;
  recent_accuracy: number;
  weighted_accuracy: number;
  target_hit_streak: number;
  review_successes: number;
  status: string;
  status_label: string;
  last_practised_at?: string | null;
  next_review_at?: string | null;
};

export type ReviewSchedule = {
  id: string;
  task_id: string;
  skill_key: string;
  due_at: string;
  status: "scheduled" | "due" | "retry" | "completed";
  completed_at?: string | null;
};

export type LearningPlan = {
  version: string;
  policy: {
    minimum_questions: number;
    required_success_days: number;
    review_delay_days: number;
    later_review_required: boolean;
    manual_completion_allowed: false;
    ai_can_mark_mastery: false;
  };
  tasks: LearningTask[];
  active_tasks: LearningTask[];
  mastered_tasks: LearningTask[];
  skill_mastery: SkillMastery[];
  review_schedule: ReviewSchedule[];
  due_reviews: ReviewSchedule[];
  active_task_count: number;
  mastered_skill_count: number;
  due_review_count: number;
};

export type SentenceTrainingStep = {
  key: "predicate" | "subject" | "object" | "scope" | "logic";
  label: string;
  prompt: string;
};
export type SentenceTrainingItem = {
  id: string;
  sentence: string;
  difficulty: string;
  source: Record<string, unknown>;
  status: "verified";
};
export type SentenceTrainingCatalog = {
  version: number;
  status: {
    item_count: number;
    bytes: number;
    sha256: string;
    verified: boolean;
  };
  steps: SentenceTrainingStep[];
  items: SentenceTrainingItem[];
  answer_fields_exposed_before_submit: false;
  ai_calls: 0;
};
export type SentenceTrainingResult = {
  item_id: string;
  sentence: string;
  score: number;
  total: number;
  accuracy: number;
  steps: Array<{
    key: string;
    correct: boolean;
    user_answer: string;
    expected_answer: string;
  }>;
  explanation: string;
  simplified_zh: string;
  answer_impact: string;
  verified_standard: true;
  ai_calls: 0;
};
export type SentenceTrainingAttempt = {
  attempt_id: string;
  item_id: string;
  created_at: string;
  idempotent_replay: boolean;
  result: SentenceTrainingResult;
};

export type PersonalSentenceAnalysis = {
  predicate?: string;
  subject?: string;
  object?: string;
  scope?: string;
  logic?: string;
  note?: string;
};
export type StandardSentenceParse = {
  predicate: string;
  subject: string;
  object: string;
  scope: string;
  logic: string;
  explanation: string;
  simplified_zh: string;
  answer_impact: string;
};
export type PersonalSentence = {
  id: string;
  sentence: string;
  previous_sentence?: string | null;
  next_sentence?: string | null;
  paragraph?: string | null;
  source_type: "reading_selection" | "wrong_evidence" | "mock_mark" | "manual";
  source_session_id?: string | null;
  source_question_id?: string | null;
  test_id?: string | null;
  test_title?: string | null;
  part_number?: number | null;
  paragraph_index?: number | null;
  exam_mode?: string | null;
  permission: "locked" | "self_only" | "verified";
  verified_item_id?: string | null;
  analysis: PersonalSentenceAnalysis;
  created_at: string;
  updated_at: string;
  deduplicated: boolean;
  standard_parse_available: boolean;
  standard_parse?: StandardSentenceParse | null;
  standard_parse_label?: string | null;
  analysis_allowed: boolean;
  ai_analysis_available: false;
};

export type PersonalSentenceCapture = {
  user_id?: string;
  sentence: string;
  previous_sentence?: string;
  next_sentence?: string;
  paragraph?: string;
  source_type: "reading_selection" | "wrong_evidence" | "mock_mark" | "manual";
  source_session_id?: string;
  source_question_id?: string;
  test_id?: string;
  test_title?: string;
  part_number?: number;
  paragraph_index?: number;
  exam_mode?: string;
};

export type VocabularySource = {
  id: string;
  source_type: "reading_text" | "question" | "option" | "wrong_review" | "sentence" | "ai" | "manual";
  source_sentence?: string | null;
  source_context?: string | null;
  source_session_id?: string | null;
  source_question_id?: string | null;
  test_id?: string | null;
  test_title?: string | null;
  part_number?: number | null;
  created_at: string;
};

export type VocabularyItem = {
  id: string;
  user_id: string;
  term: string;
  meaning: string;
  note: string;
  status: "learning" | "mastered";
  occurrence_count: number;
  sources: VocabularySource[];
  created_at: string;
  updated_at: string;
  deduplicated: boolean;
  source_added: boolean;
};

export type VocabularyCapture = {
  user_id?: string;
  term: string;
  meaning?: string;
  note?: string;
  source_type: VocabularySource["source_type"];
  source_sentence?: string;
  source_context?: string;
  source_session_id?: string;
  source_question_id?: string;
  test_id?: string;
  test_title?: string;
  part_number?: number;
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

export async function fetchLearningPlan(userId = "owner", signal?: AbortSignal): Promise<LearningPlan> {
  return apiJson<LearningPlan>(`/api/v1/plan?user_id=${encodeURIComponent(userId)}`, { signal });
}

export async function fetchSentenceTraining(signal?: AbortSignal): Promise<SentenceTrainingCatalog> {
  return apiJson<SentenceTrainingCatalog>("/api/v1/sentence-training", { signal });
}

export async function submitSentenceTraining(payload: {
  user_id?: string;
  client_submission_id: string;
  item_id: string;
  answers: Record<string, string>;
}): Promise<SentenceTrainingAttempt> {
  return apiJson<SentenceTrainingAttempt>("/api/v1/sentence-training/submit", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchPersonalSentences(userId = "owner", signal?: AbortSignal): Promise<PersonalSentence[]> {
  const data = await apiJson<{ items: PersonalSentence[] }>(
    `/api/v1/sentences?user_id=${encodeURIComponent(userId)}&limit=500`,
    { signal }
  );
  return data.items;
}

export async function capturePersonalSentence(payload: PersonalSentenceCapture): Promise<PersonalSentence> {
  return apiJson<PersonalSentence>("/api/v1/sentences", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updatePersonalSentenceAnalysis(
  sentenceId: string,
  analysis: PersonalSentenceAnalysis,
  userId = "owner"
): Promise<PersonalSentence> {
  return apiJson<PersonalSentence>(`/api/v1/sentences/${encodeURIComponent(sentenceId)}/analysis`, {
    method: "PUT",
    body: JSON.stringify({ user_id: userId, ...analysis })
  });
}

export async function deletePersonalSentence(sentenceId: string, userId = "owner"): Promise<void> {
  await apiJson<{ deleted: true }>(
    `/api/v1/sentences/${encodeURIComponent(sentenceId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
}

export async function fetchVocabulary(userId = "owner", signal?: AbortSignal): Promise<VocabularyItem[]> {
  const data = await apiJson<{ items: VocabularyItem[] }>(
    `/api/v1/vocabulary?user_id=${encodeURIComponent(userId)}&limit=5000`,
    { signal }
  );
  return data.items;
}

export async function captureVocabulary(payload: VocabularyCapture): Promise<VocabularyItem> {
  return apiJson<VocabularyItem>("/api/v1/vocabulary", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateVocabulary(
  itemId: string,
  update: { meaning: string; note: string; status: VocabularyItem["status"] },
  userId = "owner"
): Promise<VocabularyItem> {
  return apiJson<VocabularyItem>(`/api/v1/vocabulary/${encodeURIComponent(itemId)}`, {
    method: "PUT",
    body: JSON.stringify({ user_id: userId, ...update })
  });
}

export async function deleteVocabulary(itemId: string, userId = "owner"): Promise<void> {
  await apiJson<{ deleted: true }>(
    `/api/v1/vocabulary/${encodeURIComponent(itemId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
}

export function vocabularyExportUrl(format: "csv" | "txt" | "json", userId = "owner"): string {
  return `${API_BASE_URL}/api/v1/vocabulary/export?format=${format}&user_id=${encodeURIComponent(userId)}`;
}
