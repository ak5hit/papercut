"use client";

import { useState } from "react";
import { ChevronDown, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { PipelineTrace as PipelineTraceType } from "@/lib/types";

interface UploadPipelineProps {
  trace: PipelineTraceType;
}

export function UploadPipeline({ trace }: UploadPipelineProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <Button
          variant="ghost"
          onClick={() => setExpanded(!expanded)}
          className="w-full justify-start gap-2 p-0 h-auto"
        >
          <Cpu className="h-4 w-4 text-primary" />
          <span className="font-medium text-sm flex-1 text-left">
            Extractor: {trace.extractor}
          </span>
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </Button>
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0">
          <ScrollArea className="max-h-96">
            <div className="space-y-2">
              {trace.steps.map((step, i) => {
                const isError = step.step.toLowerCase().includes("failed");
                return (
                  <div key={i} className="flex items-start gap-2">
                    <Badge
                      variant={isError ? "destructive" : "secondary"}
                      className="h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px]"
                    >
                      {isError ? "\u2717" : "\u2713"}
                    </Badge>
                    <div>
                      <p className="text-sm">{step.step}</p>
                      {step.detail && (
                        <p className="text-xs text-muted-foreground">
                          {step.detail}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>

          {trace.extracted_fields &&
            Object.keys(trace.extracted_fields).length > 0 && (
              <>
                <Separator className="my-3" />
                <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                  Extracted Fields
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(trace.extracted_fields).map(([key, value]) => (
                    <Badge key={key} variant="secondary" className="text-xs">
                      {key}:{" "}
                      {Array.isArray(value)
                        ? value.join(", ")
                        : value !== null && value !== undefined
                        ? String(value)
                        : "\u2014"}
                    </Badge>
                  ))}
                </div>
              </>
            )}
        </CardContent>
      )}
    </Card>
  );
}
