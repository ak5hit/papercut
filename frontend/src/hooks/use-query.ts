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
