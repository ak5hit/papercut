"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "./markdown-renderer";
import { SourceReferences } from "./source-references";
import type { ExecutionTrace, SourceReference } from "@/lib/types";

interface StreamingAnswerProps {
  content: string;
  trace?: ExecutionTrace;
  sources?: SourceReference[];
  streaming?: boolean;
  onOpenGraph?: (documentId: string) => void;
}

export function StreamingAnswer({
  content,
  trace,
  sources,
  streaming,
  onOpenGraph,
}: StreamingAnswerProps) {
  return (
    <div className="space-y-3">
      {trace && (
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-[10px]">
            {trace.strategy}
          </Badge>
          {trace.steps && trace.steps.length > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {trace.steps.length} steps
            </span>
          )}
        </div>
      )}

      <Card>
        <CardContent className="pt-4">
          {content ? (
            <MarkdownRenderer content={content} />
          ) : (
            <div className="min-h-[1em]" />
          )}
          {streaming && (
            <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-0.5" />
          )}
        </CardContent>
      </Card>

      {sources && sources.length > 0 && (
        <SourceReferences sources={sources} onOpenGraph={onOpenGraph} />
      )}
    </div>
  );
}
