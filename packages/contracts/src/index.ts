export type ExamMode = "study" | "part_practice" | "question_type" | "ability" | "mock_exam";
export type SessionStatus = "created" | "in_progress" | "submitted" | "abandoned";

export type PublicQuestion = {
  id: string;
  number: number;
  prompt: string;
  questionType: string;
  subtype: string;
  instructions?: string;
  options?: string[];
};

export type PracticeSession = {
  id: string;
  userId: string;
  mode: ExamMode;
  status: SessionStatus;
  testId: string;
  partNumbers: number[];
  questions: PublicQuestion[];
  createdAt: string;
  submittedAt?: string;
};

export type SubmissionRequest = {
  clientSubmissionId: string;
  answers: Record<string, string | string[]>;
  elapsedSeconds: number;
};

export type BandEstimate = {
  eligible: boolean;
  rawScore: number;
  outOf: number;
  estimatedBand?: number;
  displayBand?: string;
  nextBand?: number;
  nextBandMinimumScore?: number;
  questionsToNextBand?: number;
  isOfficialResult: false;
  noticeZh?: string;
  version?: string;
};

export type SubmittedQuestionReview = {
  questionId: string;
  correct: boolean;
  userAnswer: string | string[] | null;
  correctAnswer: string | string[];
  evidence: string[];
  explanation?: string;
};

export type SubmissionResult = {
  sessionId: string;
  correctCount: number;
  totalQuestions: number;
  band: number | null;
  bandEstimate?: BandEstimate;
  reviews: SubmittedQuestionReview[];
};
