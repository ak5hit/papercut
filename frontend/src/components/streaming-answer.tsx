"use client";

import { Card, CardContent } from "@/components/ui/card";
import { MarkdownRenderer } from "./markdown-renderer";
import { SourceReferences } from "./source-references";
import type { SourceReference } from "@/lib/types";

interface StreamingAnswerProps {
  content: string;
  sources?: SourceReference[];
  streaming?: boolean;
  onOpenGraph?: (documentId?: string) => void;
}

export function StreamingAnswer({
  content,
  sources,
  streaming,
  onOpenGraph,
}: StreamingAnswerProps) {
  return (
    <div className="space-y-2">
      <Card className="rounded-2xl border-0 shadow-none bg-muted/40">
        <CardContent className="px-4 py-3">
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
