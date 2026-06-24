"use client";

import { useState, useEffect } from "react";
import { getDocumentGraph } from "@/lib/api-client";
import type { GraphData } from "@/lib/types";

export function useGraph(documentId: string | null) {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) {
      setGraphData(null);
      return;
    }

    setLoading(true);
    setError(null);
    getDocumentGraph(documentId)
      .then((data) => setGraphData(data))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load graph")
      )
      .finally(() => setLoading(false));
  }, [documentId]);

  return { graphData, loading, error };
}
