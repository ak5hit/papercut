"use client";

import { useState, useEffect } from "react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Upload, MessageCircle } from "lucide-react";
import { toast } from "sonner";

import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import { UploadDropzone } from "@/components/upload-dropzone";
import { UploadProgress } from "@/components/upload-progress";
import { ChatView } from "@/components/chat-view";
import { GraphModal } from "@/components/graph-modal";

import { useDocuments } from "@/hooks/use-documents";
import { useUpload } from "@/hooks/use-upload";
import { useChat } from "@/hooks/use-chat";
import { useReadiness } from "@/hooks/use-readiness";

export default function HomePage() {
  const { documents, loading: docsLoading, refresh, deleteDocument } = useDocuments();
  const { upload, uploading, error: uploadError, phases, docResult } = useUpload();
  const { messages, loading: chatLoading, send: chatSend, clear: chatClear, error: chatError } = useChat();
  const { isReady } = useReadiness();

  const [activeTab, setActiveTab] = useState<"upload" | "chat">("chat");
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

  const handleDelete = async (id: string) => {
    try {
      await deleteDocument(id);
      if (selectedDocId === id) setSelectedDocId(null);
      if (graphModalDocId === id) setGraphModalDocId(null);
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
        onUploadClick={() => setActiveTab("upload")}
        onDelete={handleDelete}
      />
      <SidebarInset>
        <SiteHeader />
        <main className="flex-1 p-4 md:p-6 max-w-4xl mx-auto w-full">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "upload" | "chat")}>
            <TabsList className="grid w-full grid-cols-2 mb-6">
              <TabsTrigger value="upload" className="gap-2">
                <Upload className="h-4 w-4" />
                <span className="hidden sm:inline">Upload</span>
              </TabsTrigger>
              <TabsTrigger value="chat" className="gap-2">
                <MessageCircle className="h-4 w-4" />
                <span className="hidden sm:inline">Chat</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="upload" className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold mb-3">Upload Document</h2>
                <UploadDropzone
                  onUpload={handleUpload}
                  uploading={uploading}
                  disabled={!isReady}
                  docResult={docResult}
                  uploadError={uploadError}
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
            </TabsContent>

            <TabsContent value="chat" className="space-y-4">
              <ChatView
                messages={messages}
                loading={chatLoading}
                onSend={chatSend}
                onOpenGraph={handleSelectDoc}
              />
            </TabsContent>
          </Tabs>
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
