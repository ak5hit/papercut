"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "./markdown-renderer";
import { SourceReferences } from "./source-references";
import { ExecutionTrace } from "./execution-trace";
import type { QueryResponse } from "@/lib/types";

interface AnswerDisplayProps {
  question: string;
  response: QueryResponse;
  onOpenGraph?: (documentId: string) => void;
}

export function AnswerDisplay({ question, response, onOpenGraph }: AnswerDisplayProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {response.trace.strategy}
            </Badge>
            <span className="text-xs text-muted-foreground">Question</span>
          </div>
          <p className="font-medium text-sm">{question}</p>
        </CardHeader>
        <CardContent>
          <MarkdownRenderer content={response.answer} />
        </CardContent>
      </Card>

      {response.sources.length > 0 && (
        <SourceReferences sources={response.sources} onOpenGraph={onOpenGraph} />
      )}
      <ExecutionTrace trace={response.trace} />
    </div>
  );
}
