"use client";

import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { SourceReference } from "@/lib/types";

interface SourceReferencesProps {
  sources: SourceReference[];
  onOpenGraph?: (documentId: string) => void;
}

export function SourceReferences({ sources, onOpenGraph }: SourceReferencesProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <Button
        variant="ghost"
        onClick={() => setExpanded(!expanded)}
        className="w-full justify-between p-3 h-auto"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <FileText className="h-4 w-4" />
          Sources ({sources.length})
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </Button>
      {expanded && (
        <CardContent className="pt-0">
          <ScrollArea className="max-h-60">
            <div className="space-y-2">
              {sources.map((source, i) => (
                <div key={i} className="bg-muted/50 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    {onOpenGraph ? (
                      <button
                        onClick={() => onOpenGraph(source.document_id)}
                        className="font-medium text-sm flex-1 truncate text-left hover:text-primary transition-colors"
                      >
                        {source.document_name}
                      </button>
                    ) : (
                      <p className="font-medium text-sm flex-1 truncate">
                        {source.document_name}
                      </p>
                    )}
                    {source.page !== null && (
                      <Badge variant="secondary" className="text-xs">
                        Page {source.page}
                      </Badge>
                    )}
                  </div>
                  {source.excerpt && (
                    <p className="text-xs text-muted-foreground italic line-clamp-2">
                      &quot;{source.excerpt}...&quot;
                    </p>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      )}
    </Card>
  );
}
