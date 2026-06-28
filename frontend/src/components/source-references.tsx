"use client";

import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SourceReference } from "@/lib/types";

interface SourceReferencesProps {
  sources: SourceReference[];
  onOpenGraph?: (documentId: string) => void;
}

export function SourceReferences({ sources, onOpenGraph }: SourceReferencesProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setExpanded(!expanded)}
        className="h-auto px-2 py-1 text-xs text-muted-foreground gap-1"
      >
        Sources ({sources.length})
        <ChevronDown
          className={`h-3 w-3 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </Button>
      {expanded && (
        <div className="flex flex-wrap gap-2 mt-1">
          {sources.map((source, i) => (
            onOpenGraph ? (
              <button
                key={i}
                onClick={() => onOpenGraph(source.document_id)}
                className="inline-flex items-center gap-1 rounded-full bg-muted/50 px-3 py-1 text-xs text-muted-foreground hover:text-primary hover:bg-muted/80 transition-colors"
              >
                {source.document_name}
                {source.score !== undefined && (
                  <span className="text-muted-foreground/60 tabular-nums">
                    ({source.score.toFixed(2)})
                  </span>
                )}
                <ExternalLink className="h-3 w-3 shrink-0" />
              </button>
            ) : (
              <span
                key={i}
                className="inline-flex items-center rounded-full bg-muted/50 px-3 py-1 text-xs text-muted-foreground"
              >
                {source.document_name}
                {source.score !== undefined && (
                  <span className="text-muted-foreground/60 tabular-nums">
                    ({source.score.toFixed(2)})
                  </span>
                )}
              </span>
            )
          ))}
        </div>
      )}
    </div>
  );
}
