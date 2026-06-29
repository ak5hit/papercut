"use client";

import { Loader2 } from "lucide-react";
import type { ChatProgress } from "@/lib/types";

interface QueryProgressProps {
  progress?: ChatProgress;
}

export function QueryProgress({ progress }: QueryProgressProps) {
  return (
    <div className="flex items-center gap-2 min-h-[20px]">
      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
      <span
        key={progress?.message ?? "thinking"}
        className="text-sm text-muted-foreground animate-in fade-in duration-500"
      >
        {progress?.message ?? "Thinking..."}
      </span>
    </div>
  );
}
