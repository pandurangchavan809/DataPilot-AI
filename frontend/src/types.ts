export type DbType = "sqlite_demo" | "postgresql" | "mysql";

export interface ModelInfo {
  id: string;
  label: string;
  name: string;
  provider: string;
  provider_label: string;
  roles: string[];
}

export interface ClientConfig {
  app_name: string;
  models: ModelInfo[];
  default_model: string;
  auto_model: { reasoning: string; fast: string };
  db_types: DbType[];
  limits: { row_limit: number; query_timeout_seconds: number; max_message_chars: number };
}

export interface ConnectionInfo {
  type: DbType;
  dialect: string;
  name: string;
  host: string | null;
  port: number | null;
  database: string | null;
  username: string | null;
  ssl: boolean;
}

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
}

export interface SchemaTable {
  name: string;
  is_view: boolean;
  columns: SchemaColumn[];
  foreign_keys: { columns: string[]; ref_table: string; ref_columns: string[] }[];
}

export interface SchemaInfo {
  dialect: string;
  tables: SchemaTable[];
}

export interface ConnectionState {
  connection: ConnectionInfo | null;
  schema: SchemaInfo | null;
}

export interface ConnectPayload {
  type: DbType;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
  ssl?: boolean;
}

export type StepStatus = "running" | "done" | "error" | "skipped";

export interface AgentStep {
  id: string;
  kind: string;
  label: string;
  status: StepStatus;
  detail?: string;
  duration_ms?: number;
}

export interface QueryResult {
  columns: string[];
  column_types: ("number" | "string" | "boolean" | "unknown")[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

export type ChartType = "bar" | "line" | "area" | "pie" | "scatter";

export interface ChartSpec {
  type: ChartType;
  x: string;
  y: string[];
  title: string;
  max_points: number;
}

// --- Auth ---
export interface AuthUser {
  id: number;
  email: string;
  created_at: number;
  last_login_at: number | null;
  login_count: number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface AuthResponse extends AuthTokens {
  token_type: "Bearer";
  expires_in: number;
  user: AuthUser;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}

// --- Chat messages (kept in sessionStorage only) ---

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
