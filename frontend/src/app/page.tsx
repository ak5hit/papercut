"use client";

import { UploadDropzone } from "@/components/upload-dropzone";
import { UploadPipeline } from "@/components/upload-pipeline";
import { DocumentList } from "@/components/document-list";
import { QueryInterface } from "@/components/query-interface";
import { AnswerDisplay } from "@/components/answer-display";
import { useDocuments } from "@/hooks/use-documents";
import { useUpload } from "@/hooks/use-upload";
import { useQuery } from "@/hooks/use-query";
import { useReadiness } from "@/hooks/use-readiness";
import { Loader2, Info, BookOpen, Lightbulb, Wrench } from "lucide-react";
import { useEffect, useState } from "react";

export default function HomePage() {
  const { documents, loading: docsLoading, error: docsError, refresh, deleteDocument } = useDocuments();
  const { upload, uploading, error: uploadError, lastUploaded, lastTrace } = useUpload();
  const { ask, response, loading: queryLoading, error: queryError } = useQuery();
  const [lastQuestion, setLastQuestion] = useState("");
  const { isReady, loading: readinessLoading } = useReadiness();

  // Refetch documents once backend becomes ready
  useEffect(() => {
    if (isReady) {
      refresh();
    }
  }, [isReady, refresh]);

  const handleUpload = async (file: File, documentType: string) => {
    await upload(file, documentType);
    refresh();
  };

  const handleAsk = async (question: string) => {
    setLastQuestion(question);
    await ask(question);
  };

  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">
          Document Intelligence Platform
        </h1>
        <p className="text-gray-600 mt-1">
          Upload documents. Ask questions. Get answers with evidence.
        </p>
      </header>

      <div className="flex flex-col lg:flex-row gap-8 mt-6">
        <div className="flex-1 min-w-0 space-y-8">

      {(!isReady || readinessLoading) && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-start gap-3">
          <Loader2 className="h-5 w-5 text-yellow-600 animate-spin shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-yellow-800">
              Loading embedding model...
            </p>
            <p className="text-sm text-yellow-700 mt-0.5">
              This may take 30–60 seconds on first run. Uploads will be enabled once ready.
            </p>
          </div>
        </div>
      )}

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Upload Document</h2>
        <UploadDropzone
          onUpload={handleUpload}
          uploading={uploading}
          disabled={!isReady}
        />
        {uploadError && (
          <p className="text-sm text-red-600">{uploadError}</p>
        )}
        {lastUploaded && (
          <>
            <p className="text-sm text-green-600 font-medium">
              Uploaded: {lastUploaded.filename} ({lastUploaded.page_count} pages)
            </p>
            {lastTrace && <UploadPipeline trace={lastTrace} />}
          </>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Ask a Question</h2>
        <QueryInterface onSubmit={handleAsk} loading={queryLoading} />
        {queryError && (
          <p className="text-sm text-red-600">{queryError}</p>
        )}
        {response && <AnswerDisplay question={lastQuestion} response={response} />}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-800">Documents</h2>
        {docsLoading ? (
          <p className="text-sm text-gray-500">Loading documents...</p>
        ) : !isReady ? (
          <p className="text-sm text-gray-500">System initializing, documents will load shortly...</p>
        ) : docsError ? (
          <p className="text-sm text-red-600">{docsError}</p>
        ) : (
          <DocumentList documents={documents} onDelete={deleteDocument} />
        )}
      </section>
        </div>

        <aside className="lg:w-80 shrink-0">
          <div className="sticky top-8 space-y-4">
            <section className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3">
              <div className="flex items-start gap-2">
                <Info className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
                <p className="text-sm text-blue-900">
                  A universal document intelligence platform. Upload a PDF, ask questions in natural language, and get answers with source references, page numbers, and an execution trace.
                </p>
              </div>

              <details className="group">
                <summary className="flex items-center gap-2 text-sm font-medium text-blue-900 cursor-pointer list-none">
                  <BookOpen className="h-4 w-4" />
                  <span>What does it support?</span>
                  <span className="ml-auto text-blue-600 group-open:rotate-90 transition-transform">▶</span>
                </summary>
                <ul className="text-sm text-blue-800 mt-2 ml-6 space-y-1 list-disc list-inside">
                  <li><strong>PDFs</strong> — text-based PDFs (not scanned images)</li>
                  <li><strong>Resumes</strong> — specialized extraction with structured fields</li>
                  <li><strong>Three query types</strong> — structured lookups, semantic search, or hybrid (structured filter + semantic)</li>
                </ul>
              </details>

              <details className="group">
                <summary className="flex items-center gap-2 text-sm font-medium text-blue-900 cursor-pointer list-none">
                  <Lightbulb className="h-4 w-4" />
                  <span>Try asking...</span>
                  <span className="ml-auto text-blue-600 group-open:rotate-90 transition-transform">▶</span>
                </summary>
                <ul className="text-sm text-blue-800 mt-2 ml-6 space-y-1 list-disc list-inside">
                  <li><strong>"What is &lt;name&gt;'s email address?"</strong> — structured lookup</li>
                  <li><strong>"Summarize &lt;name&gt;'s work experience"</strong> — semantic search</li>
                  <li><strong>"What did &lt;name&gt; do at CRED?"</strong> — hybrid (filter + semantic)</li>
                  <li><strong>"How is this SQL DB so scalable?"</strong> — semantic search across document excerpts</li>
                </ul>
              </details>

              <details className="group">
                <summary className="flex items-center gap-2 text-sm font-medium text-blue-900 cursor-pointer list-none">
                  <Wrench className="h-4 w-4" />
                  <span>What's extensible?</span>
                  <span className="ml-auto text-blue-600 group-open:rotate-90 transition-transform">▶</span>
                </summary>
                <p className="text-sm text-blue-800 mt-2 ml-6">
                  Adding a new extractor is straightforward — invoice, contract, receipt, CSV, DOCX, XML.
                  Create one extractor class implementing the interface, register it, and the pipeline
                  runs unchanged. The registry selects the highest-scoring extractor for each document.
                </p>
              </details>

              <p className="text-xs text-blue-700 pt-2 border-t border-blue-200">
                For architecture, tradeoffs, and implementation details, see the{' '}
                <a
                  href="https://github.com/ak5hit/papercut#readme"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-blue-900"
                >
                  README
                </a>
                .
              </p>

              <p className="text-xs text-blue-600 italic pt-2 border-t border-blue-200">
                Using cost-effective models(deepseek-v4-pro) for this demo.
                Production deployments would use higher-capacity models for faster, more accurate results.
              </p>
            </section>
          </div>
        </aside>
      </div>
    </main>
  );
}
