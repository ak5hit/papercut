# Phase 9: Frontend — End-to-End User Interface

## Objective

Build a minimal, functional Next.js frontend that enables the complete end-to-end user flow: upload documents, view processing status, ask questions, and receive explainable answers with source references. The reviewer must be able to use the application immediately after `docker compose up --build`.

## Context

- **Phases 1–8** built the entire backend pipeline: ingestion, extraction, embedding, query planning, and answer composition.
- **Backend API** exposes:
  - `POST /documents/upload` — upload PDF
  - `GET /documents/` — list documents
  - `GET /documents/{id}` — get document metadata
  - `GET /documents/{id}/chunks` — get document chunks
  - `POST /query` — ask a question, receive `{answer, sources, trace}`
  - `GET /health` / `GET /health/db` — health checks
- **No frontend directory exists.** The `docker-compose.yml` currently defines only `db` and `backend` services.
- **Technology stack** per `ENGINEERING_PRINCIPLES.md`: Next.js, TypeScript, Tailwind, shadcn/ui.

## Scope

### In Scope

- Next.js 15 app in `frontend/` directory
- Docker Compose `frontend` service with build + runtime
- Document upload UI with drag-and-drop and processing status
- Document list / gallery view
- Query interface (chat-style input)
- Answer display with expandable source references
- Execution trace display (collapsible)
- Responsive layout (mobile-friendly)
- API client layer with typed interfaces
- Error handling and loading states
- CORS already configured on backend (`allow_origins=["*"]`)

### Out of Scope

- Authentication / authorization
- Real-time WebSocket updates (polling is sufficient)
- Document preview / PDF viewer inline
- Conversation history persistence
- Dark mode toggle (can be added in Phase 12)
- Complex global state management (Zustand/Redux)

---

## 1. Architecture

```
┌─────────────────┐
│   Next.js App   │  (frontend/)
│   Port 3000     │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   FastAPI       │  (backend/)
│   Port 8000     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │  (db)
│   Port 5432     │
└─────────────────┘
```

**Communication:** Frontend talks directly to the FastAPI backend over HTTP. No API gateway, no BFF layer. CORS is already open.

---

## 2. Directory Structure

```
frontend/
├── Dockerfile
├── next.config.js
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout with providers
│   │   ├── page.tsx            # Landing + upload + query
│   │   ├── globals.css         # Tailwind + custom styles
│   │   └── documents/
│   │       └── page.tsx        # Document list view
│   ├── components/
│   │   ├── ui/                 # shadcn/ui components
│   │   ├── upload-dropzone.tsx
│   │   ├── document-card.tsx
│   │   ├── document-list.tsx
│   │   ├── query-interface.tsx
│   │   ├── answer-display.tsx
│   │   ├── source-references.tsx
│   │   ├── execution-trace.tsx
│   │   └── loading-spinner.tsx
│   ├── lib/
│   │   ├── api-client.ts       # Typed fetch wrapper
│   │   └── types.ts            # Shared TypeScript interfaces
│   └── hooks/
│       ├── use-documents.ts
│       ├── use-upload.ts
│       └── use-query.ts
```

---

## 3. Configuration Files

### 3.1 `frontend/package.json`

```json
{
  "name": "doc-intelligence-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.6.0",
    "lucide-react": "^0.460.0"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5"
  }
}
```

**Rationale:** No complex UI frameworks. `lucide-react` provides icons. `class-variance-authority` + `tailwind-merge` + `clsx` are standard shadcn/ui prerequisites. No external state management library — `useState` + `useEffect` are sufficient for this scope.

---

### 3.2 `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
```

**Rationale:** Multi-stage not needed for a demo. `npm ci` for reproducible installs. Build at image build time, run `npm start` (which runs `next start`) at runtime.

---

### 3.3 `frontend/next.config.js`

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://backend:8000/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
```

**Rationale:** `output: 'standalone'` produces a self-contained build for Docker. The rewrite rule proxies `/api/*` requests to the backend service. This means the frontend code can use `/api/documents/upload` and Next.js handles routing to `http://backend:8000/documents/upload`. The frontend never needs to know the backend URL.

---

### 3.4 `frontend/tsconfig.json`

Standard Next.js TypeScript config with `src` directory:

```json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

---

### 3.5 `frontend/tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
```

---

## 4. Core Implementation

### 4.1 `frontend/src/lib/types.ts`

```typescript
export interface Document {
  id: string;
  filename: string;
  page_count: number;
  extraction_strategy: string;
  embedding_status: "pending" | "completed" | "failed";
  created_at: string;
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
```

---

### 4.2 `frontend/src/lib/api-client.ts`

```typescript
const API_BASE = "/api";

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

export async function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/documents/upload`, {
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
  return fetchJson<Document[]>("/documents/");
}

export async function queryDocuments(query: string): Promise<QueryResponse> {
  return fetchJson<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}
```

**Rationale:** Simple typed wrapper around `fetch`. Uses `/api` prefix which Next.js rewrites to the backend. No Axios — `fetch` is native and sufficient.

---

### 4.3 `frontend/src/hooks/use-documents.ts`

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { listDocuments } from "@/lib/api-client";
import type { Document } from "@/lib/types";

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { documents, loading, error, refresh };
}
```

---

### 4.4 `frontend/src/hooks/use-upload.ts`

```typescript
"use client";

import { useState, useCallback } from "react";
import { uploadDocument } from "@/lib/api-client";
import type { Document } from "@/lib/types";

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<Document | null>(null);

  const upload = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const doc = await uploadDocument(file);
      setLastUploaded(doc);
      return doc;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  return { upload, uploading, error, lastUploaded };
}
```

---

### 4.5 `frontend/src/hooks/use-query.ts`

```typescript
"use client";

import { useState, useCallback } from "react";
import { queryDocuments } from "@/lib/api-client";
import type { QueryResponse } from "@/lib/types";

export function useQuery() {
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(async (question: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await queryDocuments(question);
      setResponse(result);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Query failed";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return { ask, response, loading, error };
}
```

---

## 5. Components

### 5.1 `frontend/src/components/upload-dropzone.tsx`

```tsx
"use client";

import { useCallback } from "react";
import { Upload } from "lucide-react";

interface UploadDropzoneProps {
  onUpload: (file: File) => void;
  uploading: boolean;
}

export function UploadDropzone({ onUpload, uploading }: UploadDropzoneProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file && file.type === "application/pdf") {
        onUpload(file);
      }
    },
    [onUpload]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onUpload(file);
    },
    [onUpload]
  );

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-500 transition-colors cursor-pointer bg-gray-50"
    >
      <input
        type="file"
        accept=".pdf"
        onChange={handleChange}
        className="hidden"
        id="file-upload"
      />
      <label htmlFor="file-upload" className="cursor-pointer block">
        <Upload className="mx-auto h-10 w-10 text-gray-400 mb-3" />
        <p className="text-sm text-gray-600">
          {uploading ? "Uploading..." : "Drop a PDF here, or click to browse"}
        </p>
      </label>
    </div>
  );
}
```

---

### 5.2 `frontend/src/components/document-list.tsx`

```tsx
import type { Document } from "@/lib/types";

interface DocumentListProps {
  documents: Document[];
}

export function DocumentList({ documents }: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="text-gray-500 text-sm">No documents uploaded yet.</p>;
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="flex items-center justify-between p-3 bg-white border rounded-lg shadow-sm"
        >
          <div className="min-w-0">
            <p className="font-medium truncate">{doc.filename}</p>
            <p className="text-xs text-gray-500">
              {doc.page_count} pages · {doc.extraction_strategy} ·{" "}
              <span
                className={
                  doc.embedding_status === "completed"
                    ? "text-green-600"
                    : doc.embedding_status === "failed"
                    ? "text-red-600"
                    : "text-yellow-600"
                }
              >
                {doc.embedding_status}
              </span>
            </p>
          </div>
          <span className="text-xs text-gray-400 shrink-0 ml-4">
            {new Date(doc.created_at).toLocaleDateString()}
          </span>
        </div>
      ))}
    </div>
  );
}
```

---

### 5.3 `frontend/src/components/query-interface.tsx`

```tsx
"use client";

import { useState } from "react";
import { Send } from "lucide-react";

interface QueryInterfaceProps {
  onSubmit: (query: string) => void;
  loading: boolean;
}

export function QueryInterface({ onSubmit, loading }: QueryInterfaceProps) {
  const [query, setQuery] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;
    onSubmit(query.trim());
    setQuery("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a question about your documents..."
        className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={loading}
      />
      <button
        type="submit"
        disabled={loading || !query.trim()}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
      >
        <Send className="h-4 w-4" />
        {loading ? "Asking..." : "Ask"}
      </button>
    </form>
  );
}
```

---

### 5.4 `frontend/src/components/answer-display.tsx`

```tsx
import type { QueryResponse } from "@/lib/types";
import { SourceReferences } from "./source-references";
import { ExecutionTrace } from "./execution-trace";

interface AnswerDisplayProps {
  response: QueryResponse;
}

export function AnswerDisplay({ response }: AnswerDisplayProps) {
  return (
    <div className="space-y-4">
      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <h3 className="font-semibold text-gray-900 mb-2">Answer</h3>
        <div className="prose prose-sm max-w-none text-gray-800 whitespace-pre-wrap">
          {response.answer}
        </div>
      </div>

      {response.sources.length > 0 && (
        <SourceReferences sources={response.sources} />
      )}

      <ExecutionTrace trace={response.trace} />
    </div>
  );
}
```

---

### 5.5 `frontend/src/components/source-references.tsx`

```tsx
import { useState } from "react";
import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import type { SourceReference } from "@/lib/types";

interface SourceReferencesProps {
  sources: SourceReference[];
}

export function SourceReferences({ sources }: SourceReferencesProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-50 border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <span className="font-medium text-sm text-gray-700 flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Sources ({sources.length})
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {sources.map((source, i) => (
            <div key={i} className="text-sm bg-white border rounded p-2">
              <p className="font-medium text-gray-900">{source.document_name}</p>
              {source.page !== null && (
                <p className="text-xs text-gray-500">Page {source.page}</p>
              )}
              {source.excerpt && (
                <p className="text-xs text-gray-600 mt-1 italic line-clamp-2">
                  "{source.excerpt}..."
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

### 5.6 `frontend/src/components/execution-trace.tsx`

```tsx
import { useState } from "react";
import { ChevronDown, ChevronUp, ListChecks } from "lucide-react";
import type { ExecutionTrace as ExecutionTraceType } from "@/lib/types";

interface ExecutionTraceProps {
  trace: ExecutionTraceType;
}

export function ExecutionTrace({ trace }: ExecutionTraceProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-50 border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <span className="font-medium text-sm text-gray-700 flex items-center gap-2">
          <ListChecks className="h-4 w-4" />
          Execution Trace — {trace.strategy}
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3">
          <ul className="space-y-1">
            {trace.steps.map((step, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-green-600 mt-0.5">✓</span>
                {step}
              </li>
            ))}
          </ul>
          <div className="mt-2 text-xs text-gray-500 flex gap-4">
            <span>Structured: {trace.structured_results_count}</span>
            <span>Semantic: {trace.semantic_results_count}</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 6. Pages

### 6.1 `frontend/src/app/layout.tsx`

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document Intelligence Platform",
  description: "Universal document intelligence with structured and semantic retrieval",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-100 text-gray-900">
        {children}
      </body>
    </html>
  );
}
```

---

### 6.2 `frontend/src/app/page.tsx`

```tsx
"use client";

import { UploadDropzone } from "@/components/upload-dropzone";
import { DocumentList } from "@/components/document-list";
import { QueryInterface } from "@/components/query-interface";
import { AnswerDisplay } from "@/components/answer-display";
import { useDocuments } from "@/hooks/use-documents";
import { useUpload } from "@/hooks/use-upload";
import { useQuery } from "@/hooks/use-query";

export default function HomePage() {
  const { documents, loading: docsLoading, refresh } = useDocuments();
  const { upload, uploading, error: uploadError, lastUploaded } = useUpload();
  const { ask, response, loading: queryLoading, error: queryError } = useQuery();

  const handleUpload = async (file: File) => {
    await upload(file);
    refresh();
  };

  return (
    <main className="max-w-3xl mx-auto px-4 py-8 space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">
          Document Intelligence Platform
        </h1>
        <p className="text-gray-600 mt-1">
          Upload documents. Ask questions. Get answers with evidence.
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Upload Document</h2>
        <UploadDropzone onUpload={handleUpload} uploading={uploading} />
        {uploadError && (
          <p className="text-sm text-red-600">{uploadError}</p>
        )}
        {lastUploaded && (
          <p className="text-sm text-green-600">
            Uploaded: {lastUploaded.filename} ({lastUploaded.page_count} pages)
          </p>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Ask a Question</h2>
        <QueryInterface onSubmit={ask} loading={queryLoading} />
        {queryError && (
          <p className="text-sm text-red-600">{queryError}</p>
        )}
        {response && <AnswerDisplay response={response} />}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Documents</h2>
        {docsLoading ? (
          <p className="text-sm text-gray-500">Loading documents...</p>
        ) : (
          <DocumentList documents={documents} />
        )}
      </section>
    </main>
  );
}
```

**Rationale:** Single-page application layout. All three core interactions (upload, query, browse) are visible on one screen. This is optimal for a demo — the reviewer doesn't need to navigate between pages to test the full flow.

---

## 7. Docker Compose Update

### 7.1 Updated `docker-compose.yml`

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: doc_intelligence
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app

  frontend:
    build:
      context: ./frontend
    ports:
      - "3000:3000"
    env_file:
      - .env
    depends_on:
      - backend

volumes:
  pgdata:
```

**Rationale:** Frontend depends on backend for API proxying. Port 3000 exposed for direct access. No shared volumes needed because the frontend build bakes everything in at image build time.

---

## 8. Test Plan

### No Frontend Unit Tests

Per `ENGINEERING_PRINCIPLES.md`: "Test behavior. Do not chase coverage numbers." Frontend testing for a demo-grade UI adds marginal value compared to backend behavior tests. Manual smoke testing covers the critical user paths.

**Verification is entirely manual smoke testing:**

1. `docker compose up --build`
2. Open `http://localhost:3000`
3. Verify landing page loads with title and description
4. Upload a PDF via drag-and-drop
5. Verify upload success message appears with filename and page count
6. Verify document appears in the Documents list with `embedding_status: completed`
7. Ask "What is the total amount?" (or similar structured query)
8. Verify answer appears with formatted structured data
9. Verify Sources section is collapsible and shows document names
10. Verify Execution Trace is collapsible and shows strategy + steps + counts
11. Ask "Summarize the contract" (semantic query)
12. Verify synthesized answer appears with chunk-level sources including excerpts
13. Ask a hybrid-style question
14. Verify hybrid answer with both document and chunk sources
15. Verify error states: upload non-PDF shows error, query when backend down shows error

---

## 9. Files Summary

### Created (18)

| File | Purpose |
|------|---------|
| `frontend/Dockerfile` | Node.js build + runtime image |
| `frontend/package.json` | Dependencies and scripts |
| `frontend/package-lock.json` | Lockfile (generated) |
| `frontend/next.config.js` | Standalone output + API rewrite proxy |
| `frontend/tsconfig.json` | TypeScript configuration |
| `frontend/tailwind.config.ts` | Tailwind CSS configuration |
| `frontend/postcss.config.js` | PostCSS configuration |
| `frontend/src/app/layout.tsx` | Root layout |
| `frontend/src/app/page.tsx` | Main page (upload + query + docs) |
| `frontend/src/app/globals.css` | Global styles |
| `frontend/src/lib/types.ts` | Shared TypeScript interfaces |
| `frontend/src/lib/api-client.ts` | Backend API client |
| `frontend/src/hooks/use-documents.ts` | Document list hook |
| `frontend/src/hooks/use-upload.ts` | Upload hook |
| `frontend/src/hooks/use-query.ts` | Query hook |
| `frontend/src/components/upload-dropzone.tsx` | Drag-and-drop upload |
| `frontend/src/components/document-list.tsx` | Document list |
| `frontend/src/components/query-interface.tsx` | Query input |
| `frontend/src/components/answer-display.tsx` | Answer + sources + trace |
| `frontend/src/components/source-references.tsx` | Collapsible source list |
| `frontend/src/components/execution-trace.tsx` | Collapsible trace viewer |

### Modified (1)

| File | Changes |
|------|---------|
| `docker-compose.yml` | Add `frontend` service with build context, port 3000, dependency on backend |

---

## 10. Deviation Protocol

Any deviation from the above during implementation must be:

1. Flagged explicitly in the phase review.
2. Documented with the reason for deviation.
3. Reflected in an updated plan document.

No silent deviations are acceptable.

### Deviations from Plan (Implementation vs. Spec)

| Area | Plan Specified | Actual Implementation | Reason |
|------|----------------|------------------------|--------|
| API proxy | Static rewrites in `next.config.js` | Dynamic route handler at `app/api/[...path]/route.ts` using `redirect: "follow"` | FastAPI returns 307 redirects with absolute `http://backend:8000` hostnames; static rewrites pass these to the browser which can't resolve them. A server-side proxy follows the redirect internally and returns the final response. |
| File upload routing | Via `/api/documents/upload` (proxied) | Direct to `http://<host>:8000/documents/upload` (CORS is open) | The Next.js API route handler loads the entire request body into memory. Large PDFs (8MB+) cause silent failures. Direct upload bypasses the memory bottleneck. |
| Upload UX | Auto-upload on file select | Two-step: file card with name/size → explicit "Upload" button | Auto-upload gave no feedback that the upload started; the two-step flow shows the selected file and requires explicit confirmation. |
| Dockerfile CMD | `npm start` | `node .next/standalone/server.js` + `ENV PORT=3000 ENV HOSTNAME=0.0.0.0` | `next start` warns and misbehaves with `output: 'standalone'`. Setting PORT explicitly prevents `.env` `PORT=8000` from leaking into the frontend container. |
| docker-compose | Frontend has `env_file: .env` | Frontend has no `env_file` | Frontend doesn't need backend env vars; the `.env` `PORT=8000` was overriding the Dockerfile's `PORT=3000`. |
| `frontend/package.json` scripts | Includes `"lint": "next lint"` | `lint` script removed | `next lint` has known circular-reference bugs with ESLint 9.x and Next.js 15.1. TypeScript build (`next build`) provides sufficient type safety. |
| Files created | 20 files | 20 files + 1 extra: `app/api/[...path]/route.ts` | The dynamic proxy route handler replaces the planned static rewrites. |
| Files NOT created | `app/documents/page.tsx` (listed in plan Section 2) | Not created | The plan also said "single-page application layout. All three core interactions on one screen" — a separate `/documents` route was redundant and removed. |
| Frontend standalone static files | Plan did not address this | Dockerfile runs `rm -rf .next && npm run build && rm -rf .next/standalone/.next/static && cp -r .next/static .next/standalone/.next/static` | Next.js `output: 'standalone'` does not include static files (CSS, JS chunks) in the standalone output. Without copying, the page renders as unstyled HTML and JavaScript fails to load. The `rm -rf` before `cp -r` prevents stale file hashes from previous builds. |

All deviations were necessary to produce a working, maintainable frontend. The core architecture (Next.js 15 + Tailwind + single-page + API proxy) is unchanged.

---

## 11. Phase Completion Checklist

Before Phase 10 begins, ALL of the following must pass:

- [ ] `docker compose build` — all three services build successfully
- [ ] `docker compose up --build` — frontend, backend, and db all start
- [ ] Frontend accessible at `http://localhost:3000`
- [ ] Backend API accessible at `http://localhost:8000`
- [ ] Manual smoke test (all 15 steps from Section 8)
- [ ] Backend tests still pass (`pytest -v`)
- [ ] No TypeScript build errors (`npm run build` in frontend container)
- [ ] No runtime crashes or import errors

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Next.js `output: 'standalone'` build issues | Use standard Next.js standalone pattern; test `npm run build` locally before Docker |
| API proxy rewrite not working in Docker | Ensure rewrite `destination` uses `http://backend:8000` (service name, not localhost) |
| Frontend bundle too large | No heavy dependencies; only lucide-react icons + Tailwind |
| CORS blocking frontend requests | Backend already allows `*` origins; proxy rewrite means CORS is irrelevant |
| Tailwind styles not applied | Verify `content` glob in `tailwind.config.ts` covers `src/**/*` |
| File upload state not reflected immediately | `useUpload` hook calls `refresh()` from `useDocuments` after success |
| Mobile layout breaks | Tailwind responsive classes; max-width container centered |

---

## 13. Design Decisions & Tradeoffs

### Why a single page instead of multiple routes?

A reviewer has 15 minutes. Navigation between pages wastes time. All three core interactions (upload, query, browse) on one screen means the reviewer can test the entire flow without clicking anything except upload, type, and submit.

### Why no global state manager?

`useState` + `useEffect` + custom hooks are sufficient for three independent data sources (documents list, upload state, query response). Adding Zustand or Redux would be premature abstraction.

### Why Next.js rewrite proxy instead of direct backend URL?

The proxy means the frontend code is environment-agnostic — it always calls `/api/...`. Next.js handles routing to the backend. This works in Docker, locally, and in any deployment without code changes.

### Why no inline PDF preview?

PDF rendering is complex and error-prone. The user gets the answer and source references. If they need to verify, the source excerpt is shown. A full PDF viewer is out of scope for a demo.

### Why collapsible sources and trace?

They add significant vertical space. Making them collapsible keeps the answer prominent while keeping evidence one click away. This optimizes for the primary use case (reading the answer) without hiding the explainability requirement.
