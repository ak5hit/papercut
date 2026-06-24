"use client";

import { Check, Loader2 } from "lucide-react";
import type { UploadPhaseState } from "@/lib/types";

interface UploadProgressProps {
  phases: UploadPhaseState[];
  totalDurationMs?: number;
}

export function UploadProgress({ phases, totalDurationMs }: UploadProgressProps) {
  return (
    <div className="space-y-2">
      {phases.map((phase) => (
        <div key={phase.key} className="flex items-center gap-3">
          <div className="h-6 w-6 shrink-0 flex items-center justify-center">
            {phase.status === "done" && (
              <div className="h-5 w-5 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
                <Check className="h-3 w-3 text-blue-600 dark:text-blue-400" />
              </div>
            )}
            {phase.status === "active" && (
              <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-blue-400" />
            )}
            {phase.status === "pending" && (
              <div className="h-5 w-5 rounded-full border-2 border-muted-foreground/30" />
            )}
            {phase.status === "error" && (
              <div className="h-5 w-5 rounded-full bg-red-100 dark:bg-red-900 flex items-center justify-center">
                <span className="text-red-600 dark:text-red-400 text-xs font-bold">!</span>
              </div>
            )}
          </div>
          <span
            className={`text-sm ${
              phase.status === "active"
                ? "font-medium text-blue-600 dark:text-blue-400"
                : phase.status === "done"
                ? "text-muted-foreground"
                : phase.status === "error"
                ? "text-destructive"
                : "text-muted-foreground/60"
            }`}
          >
            {phase.label}
          </span>
          {phase.durationMs > 0 && (
            <span className="text-xs text-muted-foreground/60 ml-auto tabular-nums">
              {(phase.durationMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      ))}
      {totalDurationMs !== undefined && totalDurationMs > 0 && (
        <p className="text-xs text-muted-foreground pt-2 border-t border-border/50 mt-2">
          Total: {(totalDurationMs / 1000).toFixed(1)}s
        </p>
      )}
    </div>
  );
}
