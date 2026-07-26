export type AiTeacherContextType = "wrong_question" | "sentence" | "plan";

export type AiTeacherMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
  cached: boolean;
  provider_request_id?: string | null;
  created_at: string;
};

export type AiTeacherConversation = {
  id: string;
  user_id: string;
  context_type: AiTeacherContextType;
  context_ref: string;
  title: string;
  summary: string;
  created_at: string;
  updated_at: string;
  messages: AiTeacherMessage[];
  usage: {
    input_tokens: number;
    output_tokens: number;
    provider_calls: number;
    cache_hits: number;
  };
};

export type AiTeacherChatPayload = {
  user_id?: string;
  context_type: AiTeacherContextType;
  question: string;
  session_id?: string;
  question_id?: string;
  sentence_id?: string;
};

export type AiTeacherChatResponse = {
  answer: string;
  cached: boolean;
  model?: string | null;
  conversation: AiTeacherConversation;
  policy: {
    can_change_answer_or_score: false;
    can_mark_mastery: false;
    daily_provider_limit: number;
    provider_calls_today?: number;
  };
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

export async function chatWithAiTeacher(payload: AiTeacherChatPayload): Promise<AiTeacherChatResponse> {
  return apiJson<AiTeacherChatResponse>("/api/v1/ai-teacher/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchAiConversations(
  userId = "owner",
  signal?: AbortSignal
): Promise<AiTeacherConversation[]> {
  const data = await apiJson<{ items: AiTeacherConversation[] }>(
    `/api/v1/ai-teacher/conversations?user_id=${encodeURIComponent(userId)}&limit=200`,
    { signal }
  );
  return data.items;
}

export async function deleteAiConversation(conversationId: string, userId = "owner"): Promise<void> {
  await apiJson<{ deleted: true }>(
    `/api/v1/ai-teacher/conversations/${encodeURIComponent(conversationId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
}
