export interface Document {
  id: string;
  filename: string;
  page_count: number;
  embedding_status: "pending" | "completed" | "failed";
  pipeline_trace?: PipelineTrace;
  created_at: string;
}

export interface UploadPhaseState {
  key: string;
  label: string;
  status: "pending" | "active" | "done" | "error";
  durationMs: number;
  startedAt?: number;
  hint?: string;
}

export interface PipelineTraceStep {
  step: string;
  detail?: string;
  duration_ms: number;
  phase: string;
}

export interface PipelineTrace {
  extractor: string;
  steps: PipelineTraceStep[];
  extracted_fields: Record<string, unknown>;
  total_duration_ms: number;
}

export interface DocumentDetail extends Document {
  raw_text_length: number;
  updated_at: string;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  text: string;
  metadata: Record<string, unknown>;
}

export interface ChatProgress {
  stage: string;
  message: string;
}

export interface SourceReference {
  document_id: string;
  document_name: string;
}

export interface ExecutionTrace {
  strategy: string;
  steps: string[];
  structured_results_count: number;
  semantic_results_count: number;
  graph_results_count: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceReference[];
  trace: ExecutionTrace;
}

export interface GraphNode {
  id: string;
  label: string;
  entity_id: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type ChatRole = "user" | "assistant";

export interface ChatRequestMessage {
  role: ChatRole;
  content: string;
}

export interface ChatResponse {
  session_id: string;
  messages: ChatRequestMessage[];
  response: QueryResponse;
}
