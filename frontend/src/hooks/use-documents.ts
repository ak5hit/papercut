"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { listDocuments, deleteDocument as apiDeleteDocument } from "@/lib/api-client";
import type { Document } from "@/lib/types";

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rollbackRef = useRef<Document[] | null>(null);

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
    setDocuments((prev) => {
      rollbackRef.current = prev;
      return prev.filter((doc) => doc.id !== id);
    });
    try {
      await apiDeleteDocument(id);
      rollbackRef.current = null;
    } catch (err) {
      if (rollbackRef.current) setDocuments(rollbackRef.current);
      rollbackRef.current = null;
      setError(err instanceof Error ? err.message : "Failed to delete document");
      throw err;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { documents, loading, error, refresh, deleteDocument };
}
