"use client";

import { CheckCircle2, Cpu } from "lucide-react";
import type { PipelineTrace as PipelineTraceType } from "@/lib/types";

interface UploadPipelineProps {
  trace: PipelineTraceType;
}

export function UploadPipeline({ trace }: UploadPipelineProps) {
  return (
    <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
      <div className="bg-blue-50 border-b px-4 py-3 flex items-center gap-2">
        <Cpu className="h-4 w-4 text-blue-600" />
        <span className="font-medium text-sm text-blue-800">
          Extractor: {trace.extractor}
        </span>
      </div>

      <div className="px-4 py-3 space-y-2">
        {trace.steps.map((step, i) => (
          <div key={i} className="flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-gray-700">{step.step}</p>
              {step.detail && (
                <p className="text-xs text-gray-500">{step.detail}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {trace.extracted_fields && Object.keys(trace.extracted_fields).length > 0 && (
        <div className="border-t px-4 py-3">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
            Extracted Fields
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(trace.extracted_fields).map(([key, value]) => (
              <div key={key} className="flex items-start gap-1">
                <span className="text-gray-500 shrink-0">{key}:</span>
                <span className="text-gray-800 font-medium truncate">
                  {Array.isArray(value)
                    ? value.join(", ")
                    : value !== null && value !== undefined
                    ? String(value)
                    : "\u2014"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
