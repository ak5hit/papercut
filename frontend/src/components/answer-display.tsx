"use client";

import { Card, CardContent } from "@/components/ui/card";
import { MarkdownRenderer } from "./markdown-renderer";
import { SourceReferences } from "./source-references";
import type { QueryResponse } from "@/lib/types";

interface AnswerDisplayProps {
  response: QueryResponse;
  onOpenGraph?: (documentId?: string) => void;
}

export function AnswerDisplay({ response, onOpenGraph }: AnswerDisplayProps) {
  return (
    <div className="space-y-2">
      <Card className="rounded-2xl border-0 shadow-none bg-muted/40">
        <CardContent className="px-4 py-3">
          <MarkdownRenderer content={response.answer} />
        </CardContent>
      </Card>

      {response.sources.length > 0 && (
        <SourceReferences sources={response.sources} onOpenGraph={onOpenGraph} />
      )}
    </div>
  );
}
