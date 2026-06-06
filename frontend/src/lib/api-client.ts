import type { Document, QueryResponse } from "./types";

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

export async function uploadDocument(file: File, documentType?: string): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  if (documentType) {
    formData.append("document_type", documentType);
  }
  const response = await fetch(`${getBackendBase()}/documents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Upload failed: ${response.status}`);
  }
  return response.json() as Promise<Document>;
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
