"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { streamUploadDocument } from "@/lib/api-client";
import type { UploadPhaseState } from "@/lib/types";

const PHASE_ORDER = ["reading", "embedding", "extracting", "building"];

function createInitialPhases(): UploadPhaseState[] {
  return [
    { key: "reading", label: "Reading document", status: "pending", durationMs: 0 },
    { key: "embedding", label: "Generating embeddings", status: "pending", durationMs: 0 },
    { key: "extracting", label: "Extracting entities", status: "pending", durationMs: 0, hint: "LLM call in progress" },
    { key: "building", label: "Building knowledge graph", status: "pending", durationMs: 0 },
  ];
}

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phases, setPhases] = useState<UploadPhaseState[]>(createInitialPhases());
  const [docResult, setDocResult] = useState<Record<string, unknown> | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
  const activeRef = useRef<number>(-1);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (docResult || error) {
      setSelectedFile(null);
      setDuplicateError(null);
    }
  }, [docResult, error]);

  const clearTimers = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback((idx: number) => {
    clearTimers();
    timerRef.current = setInterval(() => {
      const now = performance.now();
      setPhases((prev) =>
        prev.map((p, i) =>
          i === idx && p.status === "active" && p.startedAt
            ? { ...p, durationMs: Math.round(now - p.startedAt) }
            : p,
        ),
      );
    }, 200);
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
            prev.map((p) =>
              p.status === "active"
                ? { ...p, status: "done", durationMs: p.startedAt ? Math.round(performance.now() - p.startedAt) : p.durationMs }
                : p,
            ),
          );
          setDocResult(event as Record<string, unknown>);
          break;
        } else if (event.type === "error") {
          clearTimers();
          const msg = (event as { message?: string }).message || "Upload failed";
          setError(msg);
          setPhases((prev) =>
            prev.map((p) =>
              p.status === "active"
                ? { ...p, status: "error", durationMs: p.startedAt ? Math.round(performance.now() - p.startedAt) : p.durationMs }
                : p,
            ),
          );
          break;
        } else if (event.type === "phase") {
          const { phase, label } = event as unknown as { phase: string; label: string };
          const idx = PHASE_ORDER.indexOf(phase);
          if (idx === -1) continue;

          clearTimers();
          const now = performance.now();
          setPhases((prev) => {
            const prevActiveIdx = prev.findIndex((p) => p.status === "active");
            return prev.map((p, i) => {
              if (i === prevActiveIdx && i !== idx) {
                return { ...p, status: "done", durationMs: p.startedAt ? Math.round(now - p.startedAt) : p.durationMs };
              }
              if (i === idx) {
                return { ...p, status: "active", label, startedAt: now, durationMs: 0 };
              }
              return p;
            });
          });
          setTimeout(() => startTimer(idx), 0);
        }
      }
    } catch (err) {
      clearTimers();
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
      setPhases((prev) =>
        prev.map((p) =>
          p.status === "active"
            ? { ...p, status: "error", durationMs: p.startedAt ? Math.round(performance.now() - p.startedAt) : p.durationMs }
            : p,
        ),
      );
    } finally {
      clearTimers();
      setUploading(false);
      setPhases((prev) =>
        prev.map((p) =>
          p.status === "active"
            ? { ...p, status: "done", durationMs: p.startedAt ? Math.round(performance.now() - p.startedAt) : p.durationMs }
            : p,
        ),
      );
    }
  }, [clearTimers, startTimer]);

  const reset = useCallback(() => {
    setPhases(createInitialPhases());
    setDocResult(null);
    setError(null);
  }, []);

  return {
    upload, uploading, error, phases, docResult, reset,
    selectedFile, setSelectedFile, duplicateError, setDuplicateError,
  };
}
