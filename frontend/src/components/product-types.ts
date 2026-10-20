export type View =
  "Workspace" | "Copilot" | "Knowledge" | "Approvals" | "Activity" | "Settings";
export type DocumentItem = {
  id: string;
  filename: string;
  pages: number;
  chunks: number;
  status: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  error: string | null;
  embedding_model?: string;
  embedding_collection?: string;
  embedding_dimensions?: number;
};
export type Activity = {
  id: number;
  type: string;
  actor: string;
  created_at: string;
  duration_ms?: number | null;
  details: Record<string, unknown>;
};
export type PendingAction = {
  id: string;
  name: string;
  payload: { title: string; description: string; priority: string };
  status?: string;
  created_at?: string;
  conversation_id?: string;
};
export type Source = {
  chunk_id: number;
  document_id?: string;
  filename: string;
  page: number | null;
  excerpt: string;
  score: number;
};
export type Conversation = { id: string; title: string };
export type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  pending?: PendingAction;
  failed?: boolean;
};
export type ProviderInfo = {
  provider: string;
  model: string;
  state: "configured" | "not_configured" | "demo";
  verification: "not_checked" | "simulated";
};
export type SystemInfo = {
  demo: boolean;
  generation: ProviderInfo;
  embeddings: ProviderInfo & { dimensions: number; collection: string | null };
  voice: {
    stt: string;
    tts: string;
    stt_configured: boolean;
    tts_configured: boolean;
    verification: string;
  };
  indexing: {
    max_file_mb: number;
    formats: string[];
    strategy: string;
    top_k: number;
  };
};
export type ChunkPage = {
  filename: string;
  total: number;
  offset: number;
  chunks: { id: number; page: number | null; index: number; content: string }[];
};
