import type { AgentStep, ChartSpec, QueryResult } from "./api";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
  createdAt: number;
}

export type AssistantStatus = "streaming" | "done" | "error" | "stopped";

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  status: AssistantStatus;
  steps: AgentStep[];
  sql?: { sql: string; explanation: string };
  result?: QueryResult;
  chart?: ChartSpec;
  error?: { code: string; message: string };
  model?: { id: string; label: string; provider: string };
  models: string[];
  createdAt: number;
  finishedAt?: number;
}

export type ChatMessage = UserMessage | AssistantMessage;
