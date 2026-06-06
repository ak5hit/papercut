"use client";

import { useState, useEffect, useCallback } from "react";
import { listDocuments, deleteDocument as apiDeleteDocument } from "@/lib/api-client";
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

  const deleteDocument = useCallback(async (id: string) => {
    try {
      await apiDeleteDocument(id);
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { documents, loading, error, refresh, deleteDocument };
}
