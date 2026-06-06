export interface Document {
  id: string;
  filename: string;
  page_count: number;
  extraction_strategy: string;
  embedding_status: "pending" | "completed" | "failed";
  document_type: string | null;
  pipeline_trace?: PipelineTrace;
  created_at: string;
}

export interface PipelineTraceStep {
  step: string;
  detail?: string;
}

export interface PipelineTrace {
  extractor: string;
  steps: PipelineTraceStep[];
  extracted_fields: Record<string, unknown>;
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

export interface SourceReference {
  document_id: string;
  document_name: string;
  chunk_index: number | null;
  page: number | null;
  excerpt: string;
}

export interface ExecutionTrace {
  strategy: string;
  steps: string[];
  structured_results_count: number;
  semantic_results_count: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceReference[];
  trace: ExecutionTrace;
}
