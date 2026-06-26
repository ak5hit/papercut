"use client";

import { useState, useRef, useCallback } from "react";
import { streamUploadDocument } from "@/lib/api-client";
import type { UploadPhaseState } from "@/lib/types";

const PHASE_ORDER = ["reading", "embedding", "extracting", "building"];

function createInitialPhases(): UploadPhaseState[] {
  return [
    { key: "reading", label: "Reading document", status: "pending", durationMs: 0 },
    { key: "embedding", label: "Generating embeddings", status: "pending", durationMs: 0 },
    { key: "extracting", label: "Extracting entities", status: "pending", durationMs: 0 },
    { key: "building", label: "Building knowledge graph", status: "pending", durationMs: 0 },
  ];
}

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phases, setPhases] = useState<UploadPhaseState[]>(createInitialPhases());
  const [docResult, setDocResult] = useState<Record<string, unknown> | null>(null);
  const activeRef = useRef<number>(-1);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimers = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback((idx: number) => {
    clearTimers();
    timerRef.current = setInterval(() => {
      setPhases((prev) =>
        prev.map((p, i) =>
          i === idx && p.status === "active"
            ? { ...p, durationMs: p.durationMs + 100 }
            : p,
        ),
      );
    }, 100);
  }, [clearTimers]);

  const upload = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    setDocResult(null);
    setPhases(createInitialPhases());
    activeRef.current = -1;

    try {
      for await (const event of streamUploadDocument(file)) {
        if (event.type === "done") {
          clearTimers();
          setPhases((prev) =>
            prev.map((p, i) =>
              p.status === "active" ? { ...p, status: "done" } : p,
            ),
          );
          setDocResult(event as Record<string, unknown>);
          activeRef.current = -1;
          break;
        } else if (event.type === "error") {
          clearTimers();
          const msg = (event as { message?: string }).message || "Upload failed";
          setError(msg);
          setPhases((prev) =>
            prev.map((p, i) =>
              p.status === "active" ? { ...p, status: "error" } : p,
            ),
          );
          activeRef.current = -1;
          break;
        } else if (event.type === "phase") {
          const { phase, label } = event as unknown as { phase: string; label: string };
          const idx = PHASE_ORDER.indexOf(phase);
          if (idx === -1) continue;

          clearTimers();
          setPhases((prev) =>
            prev.map((p, i) => {
              if (i === activeRef.current && p.status === "active") {
                return { ...p, status: "done" };
              }
              if (i === idx) {
                return { ...p, status: "active", label };
              }
              return p;
            }),
          );
          activeRef.current = idx;
          setTimeout(() => startTimer(idx), 0);
        }
      }
    } catch (err) {
      clearTimers();
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
      setPhases((prev) =>
        prev.map((p, i) =>
          p.status === "active" ? { ...p, status: "error" } : p,
        ),
      );
      activeRef.current = -1;
    } finally {
      clearTimers();
      setUploading(false);
      // Fallback: mark any phase still stuck on "active" as done
      setPhases((prev) =>
        prev.map((p) =>
          p.status === "active" ? { ...p, status: "done" } : p,
        ),
      );
    }
  }, [clearTimers, startTimer]);

  const reset = useCallback(() => {
    setPhases(createInitialPhases());
    setDocResult(null);
    setError(null);
  }, []);

  return { upload, uploading, error, phases, docResult, reset };
}
