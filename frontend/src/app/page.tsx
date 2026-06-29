"use client";

import { useState, useEffect } from "react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import { UploadDropzone } from "@/components/upload-dropzone";
import { ArrowLeft } from "lucide-react";
import { UploadProgress } from "@/components/upload-progress";
import { ChatView } from "@/components/chat-view";
import { GraphModal } from "@/components/graph-modal";

import { useDocuments } from "@/hooks/use-documents";
import { useUpload } from "@/hooks/use-upload";
import { useChat } from "@/hooks/use-chat";
import { useReadiness } from "@/hooks/use-readiness";

export default function HomePage() {
  const { documents, loading: docsLoading, refresh, deleteDocument } = useDocuments();
  const {
    upload, uploading, error: uploadError, phases, docResult,
    selectedFile, setSelectedFile, duplicateError, setDuplicateError,
  } = useUpload();
  const { messages, loading: chatLoading, send: chatSend, clear: chatClear, error: chatError } = useChat();
  const { isReady } = useReadiness();

  const [showUpload, setShowUpload] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [graphModalDocId, setGraphModalDocId] = useState<string | null>(null);

  useEffect(() => {
    if (isReady) refresh();
  }, [isReady, refresh]);

  const handleUpload = async (file: File) => {
    try {
      await upload(file);
      toast.success("Document uploaded successfully");
      refresh();
    } catch {
      toast.error("Upload failed");
    }
  };

  const handleSelectDoc = (id: string) => {
    setSelectedDocId(id);
    setGraphModalDocId(id);
  };

  const handleOpenGraph = (id?: string) => {
    const docId = id || documents[0]?.id || null;
    setSelectedDocId(docId);
    setGraphModalDocId(docId);
  };

  const handleDelete = async (id: string) => {
    if (selectedDocId === id) setSelectedDocId(null);
    if (graphModalDocId === id) setGraphModalDocId(null);
    try {
      await deleteDocument(id);
      toast.success("Document deleted");
    } catch {
      toast.error("Failed to delete document");
    }
  };

  return (
    <SidebarProvider>
      <AppSidebar
        documents={documents}
        loading={docsLoading}
        isReady={isReady}
        selectedDocId={selectedDocId}
        onSelectDoc={handleSelectDoc}
        onUploadClick={() => setShowUpload(true)}
        onDelete={handleDelete}
      />
      <SidebarInset>
        <SiteHeader />
        <main className="flex-1 p-4 md:p-6 max-w-4xl mx-auto w-full">
          {showUpload ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Upload Document</h2>
                <Button variant="outline" size="sm" onClick={() => setShowUpload(false)} className="gap-1.5">
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Back to chat
                </Button>
              </div>
              <UploadDropzone
                onUpload={handleUpload}
                uploading={uploading}
                disabled={!isReady}
                docResult={docResult}
                uploadError={uploadError}
                selectedFile={selectedFile}
                duplicateError={duplicateError}
                onSelectFile={setSelectedFile}
                onClearFile={() => { setSelectedFile(null); setDuplicateError(null); }}
                onDuplicateError={setDuplicateError}
              />
              {uploadError && (
                <p className="text-sm text-destructive mt-2">{uploadError}</p>
              )}
              {(uploading || docResult) && (
                <div className="mt-4">
                  <UploadProgress
                    phases={phases}
                    totalDurationMs={(docResult as { pipeline_trace?: { total_duration_ms?: number } })?.pipeline_trace?.total_duration_ms}
                  />
                  {docResult && (
                    <p className="text-sm text-green-600 dark:text-green-400 font-medium mt-3">
                      Uploaded: {(docResult as { filename?: string }).filename} ({(docResult as { page_count?: number }).page_count} pages)
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <ChatView
              messages={messages}
              loading={chatLoading}
              onSend={chatSend}
              onOpenGraph={handleOpenGraph}
              hasDocuments={documents.length > 0}
            />
          )}
        </main>
      </SidebarInset>

      <GraphModal
        documentId={graphModalDocId}
        documentName={documents.find((d) => d.id === graphModalDocId)?.filename}
        onClose={() => setGraphModalDocId(null)}
      />
    </SidebarProvider>
  );
}
