"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import type { SourceReference } from "@/lib/types";

interface SourceReferencesProps {
  sources: SourceReference[];
}

export function SourceReferences({ sources }: SourceReferencesProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-50 border rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left"
      >
        <span className="font-medium text-sm text-gray-700 flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Sources ({sources.length})
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {sources.map((source, i) => (
            <div key={i} className="text-sm bg-white border rounded p-2">
              <p className="font-medium text-gray-900">{source.document_name}</p>
              {source.excerpt && (
                <p className="text-xs text-gray-600 mt-1 italic line-clamp-2">
                  &quot;{source.excerpt}...&quot;
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
