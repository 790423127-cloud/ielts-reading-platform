import type { components as ApiComponents } from "./generated";

export type { components, operations, paths, webhooks } from "./generated";

export type HealthResponse = ApiComponents["schemas"]["HealthResponse"];
export type ReadinessResponse = ApiComponents["schemas"]["ReadinessResponse"];
export type SessionSummary = ApiComponents["schemas"]["SessionSummary"];
export type ApiSessionEnvelope = ApiComponents["schemas"]["SessionEnvelope"];
export type ApiSessionSubmitRequest = ApiComponents["schemas"]["SessionSubmitRequest"];
export type ExamMode = ApiSessionSubmitRequest["exam_mode"];
