"use client";

import { useState, useCallback } from "react";
import { uploadDocument } from "@/lib/api-client";
import type { Document, PipelineTrace } from "@/lib/types";

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<Document | null>(null);
  const [lastTrace, setLastTrace] = useState<PipelineTrace | null>(null);

  const upload = useCallback(async (file: File, documentType?: string) => {
    setUploading(true);
    setError(null);
    setLastTrace(null);
    try {
      const doc = await uploadDocument(file, documentType);
      setLastUploaded(doc);
      setLastTrace(doc.pipeline_trace || null);
      return doc;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  return { upload, uploading, error, lastUploaded, lastTrace };
}
