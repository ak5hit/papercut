"use client";

import { useState } from "react";
import { ChevronDown, ListChecks } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ExecutionTraceProps {
  trace: {
    strategy: string;
    steps: string[];
    structured_results_count: number;
    semantic_results_count: number;
    graph_results_count: number;
  };
}

export function ExecutionTrace({ trace }: ExecutionTraceProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <Button
        variant="ghost"
        onClick={() => setExpanded(!expanded)}
        className="w-full justify-between p-3 h-auto"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <ListChecks className="h-4 w-4" />
          Execution Trace &mdash; {trace.strategy}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </Button>
      {expanded && (
        <CardContent className="pt-0">
          <ul className="space-y-1">
            {trace.steps.map((step, i) => (
              <li
                key={i}
                className="text-sm text-muted-foreground flex items-start gap-2"
              >
                <span className="text-green-500 mt-0.5">&#10003;</span>
                {step}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex gap-2">
            {trace.structured_results_count > 0 && (
              <Badge variant="secondary" className="text-xs">
                Structured: {trace.structured_results_count}
              </Badge>
            )}
            {trace.semantic_results_count > 0 && (
              <Badge variant="secondary" className="text-xs">
                Semantic: {trace.semantic_results_count}
              </Badge>
            )}
            {trace.graph_results_count > 0 && (
              <Badge variant="secondary" className="text-xs">
                Graph: {trace.graph_results_count}
              </Badge>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
