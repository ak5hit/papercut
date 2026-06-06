"use client";

import { useState, useEffect, useCallback } from "react";
import { checkReadiness, type ReadinessStatus } from "@/lib/api-client";

export function useReadiness() {
  const [status, setStatus] = useState<ReadinessStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const result = await checkReadiness();
    setStatus(result);
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const result = await checkReadiness();
          if (!cancelled) {
            setStatus(result);
            setLoading(false);
            if (result?.embeddings) {
              break;
            }
          }
        } catch {
          if (!cancelled) {
            setStatus(null);
            setLoading(false);
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    };

    poll();

    return () => {
      cancelled = true;
    };
  }, []);

  const isReady = status?.embeddings === true && status?.database === true;

  return { status, loading, isReady, refresh };
}
