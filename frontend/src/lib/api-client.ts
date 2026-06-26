import type { ChatRequestMessage, ChatResponse, Document, GraphData, QueryResponse } from "./types";

const API_BASE = "/api";

function getBackendBase(): string {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export interface ReadinessStatus {
  database: boolean;
  embeddings: boolean;
  model: string;
}

export async function checkReadiness(): Promise<ReadinessStatus | null> {
  try {
    const response = await fetch(`${API_BASE}/health/ready`, {
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      return null;
    }
    return response.json() as Promise<ReadinessStatus>;
  } catch {
    return null;
  }
}

export interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

export async function* streamUploadDocument(file: File): AsyncGenerator<SSEEvent> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${getBackendBase()}/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Upload failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("Response body is not readable");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      // Flush remaining buffer (the last SSE event may not have a trailing \n\n)
      if (buffer.trim()) {
        const lines = buffer.split("\n");
        let eventType = "message";
        let dataLine = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          else if (line.startsWith("data: ")) dataLine = line.slice(6).trim();
        }
        if (dataLine) {
          try {
            const data = JSON.parse(dataLine);
            yield { type: eventType, ...data };
          } catch {
            // skip malformed events
          }
        }
      }
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let eventType = "message";
      let dataLine = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLine = line.slice(6).trim();
        }
      }

      if (dataLine) {
        try {
          const data = JSON.parse(dataLine);
          yield { type: eventType, ...data };
        } catch {
          // skip malformed events
        }
      }
    }
  }
}

export async function listDocuments(): Promise<Document[]> {
  return fetchJson<Document[]>("/documents");
}

export async function queryDocuments(query: string): Promise<QueryResponse> {
  return fetchJson<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export async function getDocumentGraph(id: string): Promise<GraphData> {
  return fetchJson<GraphData>(`/graph/documents/${id}`);
}

export async function sendChatMessage(
  sessionId: string | null,
  messages: ChatRequestMessage[],
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>("/query/chat", {
    method: "POST",
    body: JSON.stringify({ messages, session_id: sessionId }),
  });
}

export async function* streamChatMessage(
  sessionId: string | null,
  messages: ChatRequestMessage[],
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${getBackendBase()}/query/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, session_id: sessionId }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("Response body is not readable");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buffer.trim()) {
        const lines = buffer.split("\n");
        let eventType = "message";
        let dataLine = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          else if (line.startsWith("data: ")) dataLine = line.slice(6).trim();
        }
        if (dataLine) {
          try {
            const data = JSON.parse(dataLine);
            yield { type: eventType, ...data };
          } catch {
            // skip malformed events
          }
        }
      }
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let eventType = "message";
      let dataLine = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLine = line.slice(6).trim();
        }
      }

      if (dataLine) {
        try {
          const data = JSON.parse(dataLine);
          yield { type: eventType, ...data };
        } catch {
          // skip malformed events
        }
      }
    }
  }
}

export async function deleteDocument(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/documents/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Delete failed: ${response.status}`);
  }
}
