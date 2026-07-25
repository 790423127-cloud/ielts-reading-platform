export type ExamMode = "study" | "part_practice" | "question_type" | "ability" | "mock_exam";
export type SessionStatus = "created" | "in_progress" | "submitted" | "abandoned";

// Transport contracts intentionally use the FastAPI JSON field names.
// UI view models may map them to camelCase inside the frontend only.
export type PublicQuestion = {
  id: string;
  number: number;
  prompt: string;
  question_type: string;
  subtype: string;
  instructions?: string | null;
  options?: string[];
};

export type PracticeSession = {
  id: string;
  user_id: string;
  mode: ExamMode;
  status: SessionStatus;
  test_id: string;
  part_numbers: number[];
  questions: PublicQuestion[];
  created_at: string;
  submitted_at?: string | null;
};

export type SubmissionRequest = {
  client_submission_id: string;
  answers: Record<string, string | string[]>;
  elapsed_seconds: number;
};

export type BandEstimate = {
  eligible: boolean;
  raw_score: number;
  out_of: number;
  estimated_band?: number | null;
  display_band?: string | null;
  next_band?: number | null;
  next_band_minimum_score?: number | null;
  questions_to_next_band?: number | null;
  is_official_result: false;
  notice_zh?: string | null;
  version?: string | null;
};

export type SubmittedQuestionReview = {
  question_id: string;
  correct: boolean;
  user_answer: string | string[] | null;
  correct_answer: string | string[];
  evidence: string[];
  explanation?: string | null;
};

export type SubmissionResult = {
  session_id: string;
  correct_count: number;
  total_questions: number;
  band: number | null;
  band_estimate?: BandEstimate | null;
  reviews: SubmittedQuestionReview[];
};
