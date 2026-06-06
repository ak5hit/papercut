"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, ListChecks } from "lucide-react";
import type { ExecutionTrace as ExecutionTraceType } from "@/lib/types";

interface ExecutionTraceProps {
  trace: ExecutionTraceType;
}

export function ExecutionTrace({ trace }: ExecutionTraceProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-50 border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <span className="font-medium text-sm text-gray-700 flex items-center gap-2">
          <ListChecks className="h-4 w-4" />
          Execution Trace — {trace.strategy}
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3">
          <ul className="space-y-1">
            {trace.steps.map((step, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-green-600 mt-0.5">✓</span>
                {step}
              </li>
            ))}
          </ul>
          <div className="mt-2 text-xs text-gray-500 flex gap-4">
            <span>Structured: {trace.structured_results_count}</span>
            <span>Semantic: {trace.semantic_results_count}</span>
          </div>
        </div>
      )}
    </div>
  );
}
