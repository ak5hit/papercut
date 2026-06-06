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
import { Loader2 } from "lucide-react";
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
    <main className="max-w-3xl mx-auto px-4 py-8 space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">
          Document Intelligence Platform
        </h1>
        <p className="text-gray-600 mt-1">
          Upload documents. Ask questions. Get answers with evidence.
        </p>
      </header>

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
    </main>
  );
}
